"""
Application configuration — loads settings from environment / .env file.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configurable settings for the Akari Scout AI agent."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Anthropic ──────────────────────────────────────────────────────
    ANTHROPIC_API_KEY: str = ""

    # Default model for complex / unclassified queries
    DEFAULT_MODEL: str = "claude-opus-4-0"

    # Fast model used for the router classifier
    ROUTER_MODEL: str = "claude-haiku-4-0"

    # ── WyScout (optional) ─────────────────────────────────────────────
    WYSCOUT_USERNAME: str = ""
    WYSCOUT_PASSWORD: str = ""

    # ── Data ───────────────────────────────────────────────────────────
    DATA_DIR: str = "./data"

    # ── Auth ───────────────────────────────────────────────────────────
    # If set, all endpoints (except /status) require this key in X-API-Key
    API_KEY: str = ""


settings = Settings()
