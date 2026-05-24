"""
Pydantic models for API requests, responses, and internal data structures.
"""

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ── Messages ───────────────────────────────────────────────────────────────

class Message(BaseModel):
    """A single message in a conversation."""

    persona: Literal["user", "assistant"] = Field(
        ..., description="Who sent this message"
    )
    message: str = Field(..., description="The message content")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the message was sent",
    )


# ── Sessions ───────────────────────────────────────────────────────────────

class Session(BaseModel):
    """Full session with message history."""

    id: str
    tenant_id: str
    label: str
    messages: list[Message] = Field(default_factory=list)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class SessionSummary(BaseModel):
    """Lightweight session representation for list endpoints."""

    id: str
    label: str


# ── API Requests ───────────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    """Request body for creating a new session."""

    tenant_id: str = Field(..., alias="tenantId")
    label: Optional[str] = None


class UpdateSessionRequest(BaseModel):
    """Request body for updating a session label."""

    label: str


class ChatRequest(BaseModel):
    """Request body for the chat endpoint."""

    message: str
    timestamp: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ── API Responses ──────────────────────────────────────────────────────────

class ChatResponse(BaseModel):
    """Response from the chat endpoint."""

    persona: Literal["assistant"] = "assistant"
    message: str
    timestamp: datetime
    metadata: Optional[dict] = None


class HealthResponse(BaseModel):
    """Response from the /status endpoint."""

    status: str
    skills_loaded: list[str]
    tools_registered: int
    database_connected: bool
