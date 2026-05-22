"""
Akari Scout AI — FastAPI Application

REST API with:
- GET  /status                          Health check
- GET  /sessions?tenantId=...           List sessions
- GET  /sessions/{sessionId}?tenantId=  Get session with messages
- PUT  /sessions                        Create session
- DELETE /sessions/{sessionId}?tenantId= Delete session
- PATCH /sessions/{sessionId}?tenantId= Update session label
- POST /chat?tenantId=...&sessionId=... Chat with the AI agent

Start with:
    uvicorn app.main:app --reload --port 8000
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

from app.config import settings
from app.models import (
    ChatRequest,
    ChatResponse,
    CreateSessionRequest,
    HealthResponse,
    Message,
    SessionSummary,
    UpdateSessionRequest,
)
from app.session_store import InMemorySessionStore
from app.skills import build_system_prompt, list_available_skills
from app.tools.registry import get_all_tools
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
    logger.info("   Data dir: %s (exists: %s)", settings.DATA_DIR, os.path.isdir(settings.DATA_DIR))
    logger.info("   Router model: %s", settings.ROUTER_MODEL)
    logger.info("   Default model: %s", settings.DEFAULT_MODEL)
    yield
    logger.info("👋 Shutting down Akari Scout AI Agent...")


# ── FastAPI app ────────────────────────────────────────────────────────────

app = FastAPI(
    title="Akari Scout AI Agent",
    description=(
        "AI-powered football scouting agent with session management, "
        "powered by the AKARI Algorithm and Anthropic Claude."
    ),
    version="1.0.0",
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
        data_dir_exists=os.path.isdir(settings.DATA_DIR),
    )


# ── Session Management ────────────────────────────────────────────────────

@app.get("/sessions", response_model=list[SessionSummary], tags=["Sessions"])
async def list_sessions(
    tenantId: str = Query(..., description="Tenant ID"),
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
    _key: str = Depends(require_api_key),
):
    """Get a session with its full message history."""
    session = session_store.get_session(tenantId, sessionId)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "id": session.id,
        "label": session.label,
        "messages": [m.model_dump() for m in session.messages],
    }


@app.put("/sessions", tags=["Sessions"])
async def create_session(body: CreateSessionRequest, _key: str = Depends(require_api_key)):
    """Create a new session for a tenant."""
    session_id = session_store.create_session(body.tenant_id, body.label)
    return {"id": session_id}


@app.delete("/sessions/{sessionId}", tags=["Sessions"])
async def delete_session(
    sessionId: str,
    tenantId: str = Query(..., description="Tenant ID"),
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
    sessionId: str = Query(..., description="Session ID"),
    _key: str = Depends(require_api_key),
):
    """Send a message to the Akari Scout AI agent.

    Flow:
    1. Load session history
    2. Classify request (router) → select model + skills
    3. Auto-label session on first message
    4. Build system prompt from selected skills
    5. Run agent loop with tools
    6. Persist messages to session
    7. Return response
    """
    # 1. Load session
    session = session_store.get_session(tenantId, sessionId)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # 2. Route — classify complexity, select model + skills
    route_result = await router.classify(body.message)

    logger.info(
        "CHAT | tenant=%s | session=%s | tier=%s | model=%s | skills=%s",
        tenantId, sessionId, route_result.tier, route_result.model, route_result.skills,
    )

    # 3. Auto-label on first message if session has default label
    if (
        len(session.messages) == 0
        and route_result.suggested_label
        and session.label == session.created_at.strftime("%Y-%m-%d %H:%M")
    ):
        session_store.update_session_label(tenantId, sessionId, route_result.suggested_label)

    # 4. Build system prompt
    system_prompt = build_system_prompt(route_result.skills)

    # 5. Convert session history to Anthropic format
    anthropic_messages: list[dict] = []
    for msg in session.messages:
        anthropic_messages.append({
            "role": msg.persona,
            "content": msg.message,
        })
    # Add the current user message
    anthropic_messages.append({"role": "user", "content": body.message})

    # 6. Run agent
    tools = get_all_tools()
    agent_response = await agent.run_agent(
        system_prompt=system_prompt,
        messages=anthropic_messages,
        tools=tools,
        model=route_result.model,
    )

    # 7. Persist messages
    now = datetime.now(timezone.utc)
    user_msg = Message(persona="user", message=body.message, timestamp=body.timestamp or now)
    assistant_msg = Message(persona="assistant", message=agent_response.text, timestamp=now)
    session_store.append_message(tenantId, sessionId, user_msg)
    session_store.append_message(tenantId, sessionId, assistant_msg)

    # 8. Return response
    return ChatResponse(
        persona="assistant",
        message=agent_response.text,
        timestamp=now,
        metadata={
            "model": agent_response.model,
            "tier": route_result.tier,
            "tools_called": agent_response.tool_calls,
            "iterations": agent_response.iterations,
            "usage": agent_response.usage,
        },
    )
