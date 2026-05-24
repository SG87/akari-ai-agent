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

    # ── Azure SQL Database ─────────────────────────────────────────────
    DB_SERVER: str = ""
    DB_NAME: str = ""
    DB_USER: str = ""
    DB_PASSWORD: str = ""

    # ── Auth ───────────────────────────────────────────────────────────
    # If set, all endpoints (except /status) require this key in X-API-Key
    API_KEY: str = ""

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
