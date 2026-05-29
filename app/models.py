"""
Pydantic models for API requests, responses, and internal data structures.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


# ── LLM Provider ──────────────────────────────────────────────────────────


class LLMProvider(str, Enum):
    """Supported LLM providers.

    Used as a query/body parameter on /chat — FastAPI auto-validates
    and renders the allowed values in the OpenAPI docs.

    Each provider carries its own configuration (API key, tier models)
    resolved from the Settings singleton.
    """

    CLAUDE = "claude"
    GPT = "gpt"

    # ── Properties resolved from Settings ──────────────────────────────

    @property
    def api_key(self) -> str:
        """Return the API key for this provider (from environment variables)."""
        from app.config import settings

        _keys = {
            LLMProvider.CLAUDE: settings.ANTHROPIC_API_KEY,
            LLMProvider.GPT: settings.OPENAI_API_KEY,
        }
        return _keys[self]

    @property
    def simple_model(self) -> str:
        """Return the SIMPLE tier model string for this provider."""
        from app.config import settings

        _models = {
            LLMProvider.CLAUDE: settings.CLAUDE_SIMPLE_MODEL,
            LLMProvider.GPT: settings.GPT_SIMPLE_MODEL,
        }
        return _models[self]

    @property
    def standard_model(self) -> str:
        """Return the STANDARD tier model string for this provider."""
        from app.config import settings

        _models = {
            LLMProvider.CLAUDE: settings.CLAUDE_STANDARD_MODEL,
            LLMProvider.GPT: settings.GPT_STANDARD_MODEL,
        }
        return _models[self]

    @property
    def complex_model(self) -> str:
        """Return the COMPLEX tier model string for this provider."""
        from app.config import settings

        _models = {
            LLMProvider.CLAUDE: settings.CLAUDE_COMPLEX_MODEL,
            LLMProvider.GPT: settings.GPT_COMPLEX_MODEL,
        }
        return _models[self]

    @property
    def tier_models(self) -> dict[str, str]:
        """Return tier → LiteLLM model string mapping for this provider."""
        return {
            "SIMPLE": self.simple_model,
            "STANDARD": self.standard_model,
            "COMPLEX": self.complex_model,
        }

    def get_model_for_tier(self, tier: str) -> str:
        """Return the LiteLLM model string for a given complexity tier.

        Falls back to the COMPLEX model if the tier is unknown.
        """
        return self.tier_models.get(tier, self.complex_model)

    def validate_api_key(self) -> None:
        """Raise ValueError if this provider's API key is not configured."""
        if not self.api_key:
            env_var = (
                "ANTHROPIC_API_KEY" if self == LLMProvider.CLAUDE
                else "OPENAI_API_KEY"
            )
            raise ValueError(
                f"Provider '{self.value}' requires a valid API key. "
                f"Please set the {env_var} environment variable."
            )


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
    metadata: Optional[dict] = Field(
        default=None,
        description="Extra info (model, tier, tools_called, etc.) — present on assistant messages",
    )


# ── Sessions ───────────────────────────────────────────────────────────────

class Session(BaseModel):
    """Full session with message history."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    session_id: str
    tenant_id: str
    user_id: str
    label: str = Field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"))
    messages: list[Message] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SessionSummary(BaseModel):
    """Lightweight session info for listing."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    session_id: str
    tenant_id: str
    user_id: str
    label: str
    message_count: int
    created_at: datetime
    updated_at: datetime


class CreateSessionRequest(BaseModel):
    """Request body for creating a new session."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    tenant_id: str
    user_id: str
    label: Optional[str] = None


class UpdateSessionRequest(BaseModel):
    """Request body for updating a session's label."""

    label: str


# ── Health ─────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    """Response model for the /status endpoint."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    status: str
    skills_loaded: list[str]
    tools_registered: int
    database_connected: bool


# ── Chat ───────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    """Request body for the chat endpoint."""

    message: str
    timestamp: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class ChatResponse(BaseModel):
    """Response body from the chat endpoint."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    session_id: str
    persona: str
    message: str
    timestamp: datetime
    metadata: Optional[dict] = None
