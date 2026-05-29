"""
Akari Scout AI — FastAPI Application

REST API with:
- GET  /status                          Health check
- GET  /sessions?tenantId=...&userId=...           List sessions
- GET  /sessions/{sessionId}?tenantId=&userId=  Get session with messages
- PUT  /sessions                        Create session
- DELETE /sessions/{sessionId}?tenantId=&userId= Delete session
- PATCH /sessions/{sessionId}?tenantId=&userId= Update session label
- POST /chat?tenantId=...&sessionId=...&userId=... Chat with the AI agent

Start with:
    uvicorn app.main:app --reload --port 8000
"""

import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import litellm
from fastapi import Depends, FastAPI, HTTPException, Query, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader

from app.config import settings
from app.models import (
    ChatRequest,
    ChatResponse,
    CreateSessionRequest,
    HealthResponse,
    LLMProvider,
    Message,
    SessionSummary,
    UpdateSessionRequest,
)
from app.session_store import InMemorySessionStore
from app.skills import build_system_prompt, list_available_skills
from app.tools.registry import get_all_tools
from app.database import db
from app import agent, router

# ── Logging ────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("akari.api")


# ── Session store ──────────────────────────────────────────────────────────

session_store = InMemorySessionStore()


# ── Lifespan ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    logger.info("🚀 Starting Akari Scout AI Agent...")
    logger.info("   Skills available: %s", list_available_skills())
    logger.info("   Tools registered: %d", len(get_all_tools()))
    logger.info("   Database: %s/%s", settings.DB_SERVER, settings.DB_NAME)
    logger.info("   Router model: %s", settings.ROUTER_MODEL)

    for p in LLMProvider:
        logger.info(
            "   %s models: simple=%s | standard=%s | complex=%s",
            p.value.upper(), p.simple_model, p.standard_model, p.complex_model,
        )

    # Initialize Langfuse tracing (if configured)
    if settings.langfuse_enabled:
        litellm.success_callback = ["langfuse"]
        litellm.failure_callback = ["langfuse"]
        # LiteLLM's Langfuse callback reads these from os.environ directly
        os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.LANGFUSE_PUBLIC_KEY)
        os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.LANGFUSE_SECRET_KEY)
        os.environ.setdefault("LANGFUSE_HOST", settings.LANGFUSE_HOST)
        logger.info("   Langfuse: enabled (%s)", settings.LANGFUSE_HOST)
    else:
        logger.info("   Langfuse: disabled (no keys configured)")

    # Export LLM API keys to os.environ so LiteLLM can find them.
    # Pydantic loads .env into the Settings object, but LiteLLM reads
    # os.environ directly — bridge the gap here.
    if settings.ANTHROPIC_API_KEY:
        os.environ.setdefault("ANTHROPIC_API_KEY", settings.ANTHROPIC_API_KEY)
    if settings.OPENAI_API_KEY:
        os.environ.setdefault("OPENAI_API_KEY", settings.OPENAI_API_KEY)

    # Connect to Azure SQL database
    db.connect()
    logger.info("   Database connected: %s", db.is_connected)

    yield

    # Cleanup
    db.close()
    logger.info("👋 Shutting down Akari Scout AI Agent...")


# ── FastAPI app ────────────────────────────────────────────────────────────

app = FastAPI(
    title="Akari Scout AI Agent",
    description=(
        "AI-powered football scouting agent with session management, "
        "powered by the AKARI Algorithm. Supports Claude (Anthropic) and GPT (OpenAI)."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

# CORS — allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth ───────────────────────────────────────────────────────────────────

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(
    api_key: str | None = Security(_api_key_header),
) -> str:
    """Validate the API key from the X-API-Key header.

    If no API_KEY is configured in settings, all requests are allowed.
    When configured, requests without a valid key receive a 401.
    """
    if not settings.API_KEY:
        return ""  # no auth configured
    if api_key != settings.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return api_key


# ── Health ─────────────────────────────────────────────────────────────────

@app.get("/status", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Check the status of the API and its dependencies."""
    return HealthResponse(
        status="healthy",
        skills_loaded=list_available_skills(),
        tools_registered=len(get_all_tools()),
        database_connected=db.is_connected,
    )


# ── Session Management ────────────────────────────────────────────────────

@app.get("/sessions", response_model=list[SessionSummary], tags=["Sessions"])
async def list_sessions(
    tenantId: str = Query(..., description="Tenant ID"),
    userId: str = Query(..., description="User ID"),
    count: int = Query(10, description="Number of sessions to return"),
    page: int = Query(1, description="Page number"),
    _key: str = Depends(require_api_key),
):
    """Get a paginated list of sessions for a tenant."""
    return session_store.list_sessions(tenantId, count, page)


@app.get("/sessions/{sessionId}", tags=["Sessions"])
async def get_session(
    sessionId: str,
    tenantId: str = Query(..., description="Tenant ID"),
    userId: str = Query(..., description="User ID"),
    _key: str = Depends(require_api_key),
):
    """Get a session with its full message history."""
    session = session_store.get_session(tenantId, sessionId)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "sessionId": session.session_id,
        "tenantId": session.tenant_id,
        "userId": session.user_id,
        "label": session.label,
        "messages": [m.model_dump() for m in session.messages],
    }


@app.put("/sessions", tags=["Sessions"])
async def create_session(body: CreateSessionRequest, _key: str = Depends(require_api_key)):
    """Create a new session for a tenant."""
    session_id = session_store.create_session(body.tenant_id, body.user_id, body.label)
    return {"sessionId": session_id}


@app.delete("/sessions/{sessionId}", tags=["Sessions"])
async def delete_session(
    sessionId: str,
    tenantId: str = Query(..., description="Tenant ID"),
    userId: str = Query(..., description="User ID"),
    _key: str = Depends(require_api_key),
):
    """Delete a session."""
    success = session_store.delete_session(tenantId, sessionId)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"success": True}


@app.patch("/sessions/{sessionId}", tags=["Sessions"])
async def update_session(
    sessionId: str,
    body: UpdateSessionRequest,
    tenantId: str = Query(..., description="Tenant ID"),
    userId: str = Query(..., description="User ID"),
    _key: str = Depends(require_api_key),
):
    """Update a session's label."""
    success = session_store.update_session_label(tenantId, sessionId, body.label)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"success": True}


# ── Chat ───────────────────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(
    body: ChatRequest,
    tenantId: str = Query(..., description="Tenant ID"),
    userId: str = Query(..., description="User ID"),
    sessionId: str | None = Query(None, description="Session ID (optional — a new session is created if omitted)"),
    provider: LLMProvider | None = Query(
        None,
        description="LLM provider",
    ),
    _key: str = Depends(require_api_key),
):
    """Send a message to the Akari Scout AI agent.

    Flow:
    1. Resolve provider (query param or default)
    2. Validate provider API key
    3. Load or create session
    4. Classify request (router) → select model + skills
    5. Auto-label session on first message
    6. Build system prompt from selected skills
    7. Run agent loop with tools (via LiteLLM)
    8. Persist messages to session
    9. Return response
    """
    # 1. Resolve provider: query param or default to Claude
    effective_provider = provider or LLMProvider.CLAUDE

    # 2. Validate provider API key is configured
    try:
        effective_provider.validate_api_key()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # 3. Load or create session
    if sessionId:
        session = session_store.get_session(tenantId, sessionId)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
    else:
        sessionId = session_store.create_session(tenantId, userId)
        session = session_store.get_session(tenantId, sessionId)

    # 4. Route — classify complexity, select model + skills for this provider
    route_result = await router.classify(body.message, provider=effective_provider)
    effective_model = route_result.model

    logger.info(
        "CHAT | tenant=%s | session=%s | provider=%s | tier=%s | model=%s | skills=%s",
        tenantId, sessionId, effective_provider.value, route_result.tier,
        effective_model, route_result.skills,
    )

    # 5. Auto-label on first message if session has default label
    if (
        len(session.messages) == 0
        and route_result.suggested_label
        and session.label == session.created_at.strftime("%Y-%m-%d %H:%M")
    ):
        session_store.update_session_label(tenantId, sessionId, route_result.suggested_label)

    # 7. Build system prompt
    system_prompt = build_system_prompt(route_result.skills)

    # 8. Convert session history to message format
    history_messages: list[dict] = []
    for msg in session.messages:
        history_messages.append({
            "role": msg.persona,
            "content": msg.message,
        })
    # Add the current user message
    history_messages.append({"role": "user", "content": body.message})

    # 9. Build trace context for Langfuse
    trace_context = {
        "trace_id": str(uuid.uuid4()),
        "session_id": sessionId,
        "tenant_id": tenantId,
        "tier": route_result.tier,
    }

    # 10. Run agent (via LiteLLM)
    tools = get_all_tools()
    agent_response = await agent.run_agent(
        system_prompt=system_prompt,
        messages=history_messages,
        tools=tools,
        model=effective_model,
        trace_context=trace_context,
    )

    # 11. Persist messages
    now = datetime.now(timezone.utc)
    user_msg = Message(persona="user", message=body.message, timestamp=body.timestamp or now)
    assistant_msg = Message(
        persona="assistant",
        message=agent_response.text,
        timestamp=now,
        metadata={
            "model": agent_response.model,
            "provider": effective_provider.value,
            "tier": route_result.tier,
            "toolsCalled": agent_response.tool_calls,
            "iterations": agent_response.iterations,
            "usage": agent_response.usage,
        },
    )
    session_store.append_message(tenantId, sessionId, user_msg)
    session_store.append_message(tenantId, sessionId, assistant_msg)

    # 12. Return response
    return ChatResponse(
        session_id=sessionId,
        persona="assistant",
        message=agent_response.text,
        timestamp=now,
        metadata={
            "model": agent_response.model,
            "provider": effective_provider.value,
            "tier": route_result.tier,
            "toolsCalled": agent_response.tool_calls,
            "iterations": agent_response.iterations,
            "usage": agent_response.usage,
        },
    )

