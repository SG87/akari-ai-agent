"""
API integration tests for the Akari Scout AI Agent.

Tests the full HTTP request/response cycle through FastAPI using HTTPX's ASGI
transport — no live server, no real LLM calls, no real database.

Run with:
    pytest tests/ -v
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from dataclasses import dataclass, field

import pytest
import httpx

from tests.conftest import HEADERS, TENANT_ID


# ═══════════════════════════════════════════════════════════════════════════
#  /status
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_status_returns_healthy(client: httpx.AsyncClient):
    """GET /status should return 200 with status=healthy (no auth needed)."""
    resp = await client.get("/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert isinstance(data["skills_loaded"], list)
    assert isinstance(data["tools_registered"], int)
    assert "database_connected" in data


@pytest.mark.asyncio
async def test_status_no_auth_required(client: httpx.AsyncClient):
    """GET /status should work without an API key."""
    resp = await client.get("/status")  # no headers
    assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
#  Auth
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_missing_api_key_returns_401(client: httpx.AsyncClient):
    """Protected endpoints should reject requests without X-API-Key."""
    resp = await client.get("/sessions", params={"tenantId": TENANT_ID})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_wrong_api_key_returns_401(client: httpx.AsyncClient):
    """Protected endpoints should reject invalid API keys."""
    resp = await client.get(
        "/sessions",
        params={"tenantId": TENANT_ID},
        headers={"X-API-Key": "wrong-key-12345"},
    )
    assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
#  Sessions — CRUD
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_create_session(client: httpx.AsyncClient):
    """PUT /sessions should create a session and return its ID."""
    resp = await client.put(
        "/sessions",
        json={"tenantId": TENANT_ID, "label": "My Scout Session"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert isinstance(data["id"], str)


@pytest.mark.asyncio
async def test_create_session_default_label(client: httpx.AsyncClient):
    """PUT /sessions without a label should still succeed."""
    resp = await client.put(
        "/sessions",
        json={"tenantId": TENANT_ID},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert "id" in resp.json()


@pytest.mark.asyncio
async def test_list_sessions(client: httpx.AsyncClient, session_id: str):
    """GET /sessions should return a list containing the created session."""
    resp = await client.get(
        "/sessions",
        params={"tenantId": TENANT_ID},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    sessions = resp.json()
    assert isinstance(sessions, list)
    ids = [s["id"] for s in sessions]
    assert session_id in ids


@pytest.mark.asyncio
async def test_list_sessions_pagination(client: httpx.AsyncClient):
    """GET /sessions should respect count and page params."""
    # Create 3 sessions
    for i in range(3):
        await client.put(
            "/sessions",
            json={"tenantId": TENANT_ID, "label": f"Session {i}"},
            headers=HEADERS,
        )

    # Request page 1, count 2
    resp = await client.get(
        "/sessions",
        params={"tenantId": TENANT_ID, "count": 2, "page": 1},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert len(resp.json()) <= 2


@pytest.mark.asyncio
async def test_get_session(client: httpx.AsyncClient, session_id: str):
    """GET /sessions/{id} should return the full session with messages."""
    resp = await client.get(
        f"/sessions/{session_id}",
        params={"tenantId": TENANT_ID},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == session_id
    assert data["label"] == "Test Session"
    assert isinstance(data["messages"], list)


@pytest.mark.asyncio
async def test_get_session_not_found(client: httpx.AsyncClient):
    """GET /sessions/{id} with a bogus ID should return 404."""
    resp = await client.get(
        "/sessions/does-not-exist",
        params={"tenantId": TENANT_ID},
        headers=HEADERS,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_session_label(client: httpx.AsyncClient, session_id: str):
    """PATCH /sessions/{id} should update the label."""
    resp = await client.patch(
        f"/sessions/{session_id}",
        params={"tenantId": TENANT_ID},
        json={"label": "Updated Label"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # Verify the update
    get_resp = await client.get(
        f"/sessions/{session_id}",
        params={"tenantId": TENANT_ID},
        headers=HEADERS,
    )
    assert get_resp.json()["label"] == "Updated Label"


@pytest.mark.asyncio
async def test_update_session_not_found(client: httpx.AsyncClient):
    """PATCH /sessions/{id} with a bogus ID should return 404."""
    resp = await client.patch(
        "/sessions/does-not-exist",
        params={"tenantId": TENANT_ID},
        json={"label": "Nope"},
        headers=HEADERS,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_session(client: httpx.AsyncClient, session_id: str):
    """DELETE /sessions/{id} should remove the session."""
    resp = await client.delete(
        f"/sessions/{session_id}",
        params={"tenantId": TENANT_ID},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # Verify it's gone
    get_resp = await client.get(
        f"/sessions/{session_id}",
        params={"tenantId": TENANT_ID},
        headers=HEADERS,
    )
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_session_not_found(client: httpx.AsyncClient):
    """DELETE /sessions/{id} with a bogus ID should return 404."""
    resp = await client.delete(
        "/sessions/does-not-exist",
        params={"tenantId": TENANT_ID},
        headers=HEADERS,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_session_isolation_between_tenants(client: httpx.AsyncClient, session_id: str):
    """Sessions should be scoped to tenant — a different tenant can't see them."""
    resp = await client.get(
        f"/sessions/{session_id}",
        params={"tenantId": "other-tenant"},
        headers=HEADERS,
    )
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
#  /chat — Various query types
# ═══════════════════════════════════════════════════════════════════════════

def _mock_router_result(tier="STANDARD", skills=None, label=None, provider=None):
    """Build a mock RouterResult."""
    from app.router import RouterResult
    from app.models import LLMProvider

    provider = provider or LLMProvider.CLAUDE
    return RouterResult(
        model=provider.get_model_for_tier(tier),
        skills=skills or ["scout-search"],
        suggested_label=label,
        tier=tier,
    )


def _mock_agent_response(text="Mocked agent response.", tool_calls=None):
    """Build a mock AgentResponse."""
    from app.providers.base import AgentResponse

    return AgentResponse(
        text=text,
        model="anthropic/claude-sonnet-4-0",
        tool_calls=tool_calls or [],
        usage={"input_tokens": 100, "output_tokens": 50},
        iterations=1,
    )


async def _send_chat(
    client, session_id, message,
    router_result=None, agent_response=None,
    provider="claude",
):
    """Helper: send a chat message with mocked router + agent."""
    from app.models import LLMProvider

    # Convert string provider to enum for mock builder
    provider_enum = LLMProvider(provider) if isinstance(provider, str) else provider
    router_result = router_result or _mock_router_result(provider=provider_enum)
    agent_response = agent_response or _mock_agent_response()

    with (
        patch("app.main.router.classify", new_callable=AsyncMock, return_value=router_result),
        patch("app.main.agent.run_agent", new_callable=AsyncMock, return_value=agent_response),
    ):
        return await client.post(
            "/chat",
            params={"tenantId": TENANT_ID, "sessionId": session_id},
            json={"message": message, "provider": provider if isinstance(provider, str) else provider.value},
            headers=HEADERS,
        )


# ── Simple greeting ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_simple_greeting(client: httpx.AsyncClient, session_id: str):
    """A simple greeting should be routed to SIMPLE tier with no tools."""
    router_result = _mock_router_result(
        tier="SIMPLE",
        skills=[],
        label="Greeting",
    )
    agent_resp = _mock_agent_response(
        text="Hello! I'm the Akari Scout AI. How can I help you find players today?",
        tool_calls=[],
    )
    resp = await _send_chat(client, session_id, "Hi there!", router_result, agent_resp)

    assert resp.status_code == 200
    data = resp.json()
    assert data["persona"] == "assistant"
    assert "Akari" in data["message"]
    assert data["metadata"]["tier"] == "SIMPLE"
    assert data["metadata"]["tools_called"] == []


# ── Player search ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_player_search(client: httpx.AsyncClient, session_id: str):
    """A player search query should route to STANDARD with scout-search skill."""
    router_result = _mock_router_result(
        tier="STANDARD",
        skills=["scout-search"],
        label="U21 Left Wingers Croatia",
    )
    agent_resp = _mock_agent_response(
        text="I found 5 young left wingers in Croatian leagues...",
        tool_calls=["search_players", "check_transfermarkt"],
    )
    resp = await _send_chat(
        client, session_id,
        "Find me left wingers under 21 in Croatia",
        router_result, agent_resp,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["metadata"]["tier"] == "STANDARD"
    assert "search_players" in data["metadata"]["tools_called"]


# ── Player comparison ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_player_comparison(client: httpx.AsyncClient, session_id: str):
    """Comparing two players should use scout-analysis skill."""
    router_result = _mock_router_result(
        tier="STANDARD",
        skills=["scout-analysis"],
        label="Compare Messi vs Ronaldo",
    )
    agent_resp = _mock_agent_response(
        text="Here's a detailed comparison between the two players...",
        tool_calls=["search_players", "get_player_profile", "get_player_profile"],
    )
    resp = await _send_chat(
        client, session_id,
        "Compare Messi and Ronaldo",
        router_result, agent_resp,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["metadata"]["tier"] == "STANDARD"
    assert data["metadata"]["tools_called"].count("get_player_profile") == 2


# ── Complex scouting workflow ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_complex_scouting(client: httpx.AsyncClient, session_id: str):
    """A multi-step scouting request should route to COMPLEX tier with both skills."""
    router_result = _mock_router_result(
        tier="COMPLEX",
        skills=["scout-search", "scout-analysis"],
        label="CB Replacement Bundesliga",
    )
    agent_resp = _mock_agent_response(
        text="Based on my analysis across multiple leagues, here are 3 replacement options...",
        tool_calls=[
            "search_players", "get_player_profile", "get_similar_players",
            "check_transfermarkt", "check_transfermarkt", "check_transfermarkt",
        ],
    )
    resp = await _send_chat(
        client, session_id,
        "Our starting CB is leaving. Find me a replacement under 25 from Bundesliga or Eredivisie, "
        "budget 10M, must be good in the air and progressive passing",
        router_result, agent_resp,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["metadata"]["tier"] == "COMPLEX"
    assert len(data["metadata"]["tools_called"]) >= 3


# ── Stat leader query ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_stat_leaders(client: httpx.AsyncClient, session_id: str):
    """Asking for stat leaders should call the get_stat_leaders tool."""
    router_result = _mock_router_result(
        tier="STANDARD",
        skills=["scout-analysis"],
        label="Top Scorers Pro League",
    )
    agent_resp = _mock_agent_response(
        text="Here are the top scorers in the Pro League this season...",
        tool_calls=["get_stat_leaders"],
    )
    resp = await _send_chat(
        client, session_id,
        "Who are the top scorers in the Belgian Pro League?",
        router_result, agent_resp,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert "get_stat_leaders" in data["metadata"]["tools_called"]


# ── Similar players query ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_similar_players(client: httpx.AsyncClient, session_id: str):
    """Finding similar players should call get_similar_players."""
    router_result = _mock_router_result(
        tier="STANDARD",
        skills=["scout-search"],
        label="Players like De Bruyne",
    )
    agent_resp = _mock_agent_response(
        text="Here are players with a similar profile to De Bruyne...",
        tool_calls=["search_players", "get_similar_players"],
    )
    resp = await _send_chat(
        client, session_id,
        "Find me players similar to De Bruyne",
        router_result, agent_resp,
    )

    assert resp.status_code == 200
    assert "get_similar_players" in resp.json()["metadata"]["tools_called"]


# ── Chat with non-existent session ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_session_not_found(client: httpx.AsyncClient):
    """POST /chat with a bogus session ID should return 404."""
    with patch("app.main.router.classify", new_callable=AsyncMock):
        resp = await client.post(
            "/chat",
            params={"tenantId": TENANT_ID, "sessionId": "nonexistent"},
            json={"message": "Hello"},
            headers=HEADERS,
        )
    assert resp.status_code == 404


# ── Chat missing required params ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_missing_tenant_id(client: httpx.AsyncClient, session_id: str):
    """POST /chat without tenantId should return 422 (validation error)."""
    resp = await client.post(
        "/chat",
        params={"sessionId": session_id},
        json={"message": "Hello"},
        headers=HEADERS,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_chat_missing_message_body(client: httpx.AsyncClient, session_id: str):
    """POST /chat without a message body should return 422."""
    resp = await client.post(
        "/chat",
        params={"tenantId": TENANT_ID, "sessionId": session_id},
        json={},
        headers=HEADERS,
    )
    assert resp.status_code == 422


# ── Provider validation ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_unknown_provider_returns_422(client: httpx.AsyncClient, session_id: str):
    """POST /chat with an unknown provider should return 422 (enum validation)."""
    resp = await client.post(
        "/chat",
        params={"tenantId": TENANT_ID, "sessionId": session_id},
        json={"message": "Hello", "provider": "llama"},
        headers=HEADERS,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_chat_unconfigured_provider_returns_422(client: httpx.AsyncClient, session_id: str):
    """POST /chat with a provider whose API key is missing should return 422."""
    from app.config import settings

    # Temporarily clear the OpenAI key to simulate an unconfigured provider
    original_key = settings.OPENAI_API_KEY
    settings.OPENAI_API_KEY = ""
    try:
        resp = await client.post(
            "/chat",
            params={"tenantId": TENANT_ID, "sessionId": session_id},
            json={"message": "Hello", "provider": "gpt"},
            headers=HEADERS,
        )
        assert resp.status_code == 422
        assert "requires a valid API key" in resp.json()["detail"]
    finally:
        settings.OPENAI_API_KEY = original_key


@pytest.mark.asyncio
async def test_chat_provider_query_param_overrides_body(client: httpx.AsyncClient, session_id: str):
    """Provider in query param should take precedence over body field."""
    from app.models import LLMProvider

    router_result = _mock_router_result(tier="STANDARD", provider=LLMProvider.GPT)
    agent_resp = _mock_agent_response(text="Response from GPT")

    with (
        patch("app.main.router.classify", new_callable=AsyncMock, return_value=router_result),
        patch("app.main.agent.run_agent", new_callable=AsyncMock, return_value=agent_resp) as mock_agent,
    ):
        resp = await client.post(
            "/chat",
            params={
                "tenantId": TENANT_ID,
                "sessionId": session_id,
                "provider": "gpt",  # query param
            },
            json={"message": "Test", "provider": "claude"},  # body says claude
            headers=HEADERS,
        )

    assert resp.status_code == 200
    # Agent should be called with a GPT model, not Claude
    call_kwargs = mock_agent.call_args
    assert call_kwargs.kwargs["model"] == LLMProvider.GPT.standard_model


# ═══════════════════════════════════════════════════════════════════════════
#  Response format & metadata
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_chat_response_has_required_fields(client: httpx.AsyncClient, session_id: str):
    """ChatResponse should have persona, message, timestamp, and metadata."""
    resp = await _send_chat(client, session_id, "Test query")
    assert resp.status_code == 200

    data = resp.json()
    assert "persona" in data
    assert "message" in data
    assert "timestamp" in data
    assert "metadata" in data
    assert "model" in data["metadata"]
    assert "provider" in data["metadata"]
    assert "tier" in data["metadata"]
    assert "tools_called" in data["metadata"]
    assert "iterations" in data["metadata"]
    assert "usage" in data["metadata"]


@pytest.mark.asyncio
async def test_chat_persists_messages(client: httpx.AsyncClient, session_id: str):
    """After a chat, both user and assistant messages should be in the session."""
    await _send_chat(client, session_id, "Hello scout!")

    resp = await client.get(
        f"/sessions/{session_id}",
        params={"tenantId": TENANT_ID},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    messages = resp.json()["messages"]

    assert len(messages) == 2
    assert messages[0]["persona"] == "user"
    assert messages[0]["message"] == "Hello scout!"
    assert messages[0]["metadata"] is None  # user messages have no metadata
    assert messages[1]["persona"] == "assistant"
    assert messages[1]["metadata"] is not None
    assert "model" in messages[1]["metadata"]
    assert "provider" in messages[1]["metadata"]
    assert "tier" in messages[1]["metadata"]
    assert "tools_called" in messages[1]["metadata"]
    assert "iterations" in messages[1]["metadata"]
    assert "usage" in messages[1]["metadata"]


@pytest.mark.asyncio
async def test_chat_multi_turn_conversation(client: httpx.AsyncClient, session_id: str):
    """Multiple chat rounds should accumulate messages in the session."""
    await _send_chat(client, session_id, "Find left wingers in Belgium")
    await _send_chat(client, session_id, "Now filter for under 21")
    await _send_chat(client, session_id, "Sort by AKARI Potential")

    resp = await client.get(
        f"/sessions/{session_id}",
        params={"tenantId": TENANT_ID},
        headers=HEADERS,
    )
    messages = resp.json()["messages"]
    assert len(messages) == 6  # 3 user + 3 assistant


# ═══════════════════════════════════════════════════════════════════════════
#  Auto-labelling
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_chat_auto_labels_new_session(client: httpx.AsyncClient):
    """First message in a new session should auto-set the label from router."""
    # Create a session whose label matches the default date format
    resp = await client.put(
        "/sessions",
        json={"tenantId": TENANT_ID},  # no label → defaults to datetime
        headers=HEADERS,
    )
    new_session_id = resp.json()["id"]

    router_result = _mock_router_result(
        tier="STANDARD",
        skills=["scout-search"],
        label="U21 Left Wingers Belgium",
    )
    await _send_chat(
        client, new_session_id,
        "Find U21 left wingers in Belgium",
        router_result,
    )

    # Check the label was updated
    resp = await client.get(
        f"/sessions/{new_session_id}",
        params={"tenantId": TENANT_ID},
        headers=HEADERS,
    )
    assert resp.json()["label"] == "U21 Left Wingers Belgium"


# ═══════════════════════════════════════════════════════════════════════════
#  Router model selection
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_chat_uses_provider_tier_model(client: httpx.AsyncClient, session_id: str):
    """POST /chat should use the model selected by the router for the given provider."""
    from app.models import LLMProvider

    router_result = _mock_router_result(tier="STANDARD")
    agent_resp = _mock_agent_response(text="Response from default model")

    with (
        patch("app.main.router.classify", new_callable=AsyncMock, return_value=router_result),
        patch("app.main.agent.run_agent", new_callable=AsyncMock, return_value=agent_resp) as mock_agent,
    ):
        resp = await client.post(
            "/chat",
            params={"tenantId": TENANT_ID, "sessionId": session_id},
            json={"message": "Standard query"},
            headers=HEADERS,
        )

    assert resp.status_code == 200
    call_kwargs = mock_agent.call_args
    assert call_kwargs.kwargs["model"] == LLMProvider.CLAUDE.standard_model
