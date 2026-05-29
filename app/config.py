"""
Application configuration — loads settings from environment / .env file.

Per-provider model tiers use LiteLLM model strings (e.g.
'anthropic/claude-opus-4-0', 'gpt-4o'). The LLMProvider enum in models.py
resolves these into provider-specific properties.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configurable settings for the Akari Scout AI agent."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Auth ───────────────────────────────────────────────────────────
    API_KEY: str = ""

    # ── LLM API keys ──────────────────────────────────────────────────
    # LiteLLM reads these from env automatically when calling the
    # respective provider. Keep them here so pydantic validates presence.
    ANTHROPIC_API_KEY: str
    OPENAI_API_KEY: str = ""

    # ── Claude model tiers (LiteLLM strings) ──────────────────────────
    CLAUDE_SIMPLE_MODEL: str
    CLAUDE_STANDARD_MODEL: str
    CLAUDE_COMPLEX_MODEL: str

    # ── GPT model tiers (LiteLLM strings) ─────────────────────────────
    GPT_SIMPLE_MODEL: str = ""
    GPT_STANDARD_MODEL: str = ""
    GPT_COMPLEX_MODEL: str = ""

    # Fast model used for the router classifier
    ROUTER_MODEL: str

    # ── Langfuse (optional) ────────────────────────────────────────────
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_HOST: str = ""

    # ── WyScout (optional) ─────────────────────────────────────────────
    WYSCOUT_USERNAME: str = ""
    WYSCOUT_PASSWORD: str = ""

    # ── Azure SQL Database ─────────────────────────────────────────────
    DB_SERVER: str = ""
    DB_NAME: str = ""
    DB_USER: str = ""
    DB_PASSWORD: str = ""

    # ── Azure Cosmos DB (session storage) ─────────────────────────────
    COSMOS_ENDPOINT: str = ""
    COSMOS_KEY: str = ""
    COSMOS_DATABASE: str = "akari_sessions"
    COSMOS_CONTAINER: str = "sessions"
    SESSION_STORE_BACKEND: str = "memory"  # "memory" or "cosmos"

    # ── Derived helpers ────────────────────────────────────────────────

    @property
    def langfuse_enabled(self) -> bool:
        """True if Langfuse credentials are configured."""
        return bool(self.LANGFUSE_PUBLIC_KEY and self.LANGFUSE_SECRET_KEY)

    @property
    def connection_string(self) -> str:
        """Build ODBC connection string for Azure SQL."""
        return (
            f"Driver={{ODBC Driver 18 for SQL Server}};"
            f"Server=tcp:{self.DB_SERVER},1433;"
            f"Database={self.DB_NAME};"
            f"Uid={self.DB_USER};"
            f"Pwd={self.DB_PASSWORD};"
            f"Encrypt=yes;"
            f"TrustServerCertificate=no;"
            f"Connection Timeout=30;"
        )


settings = Settings()
