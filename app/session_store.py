"""
In-memory session store with a protocol-based interface for easy swapping.

Replace the InMemorySessionStore with a Cosmos DB / Redis / Postgres
implementation by conforming to the same SessionStore protocol.
"""

import uuid
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from app.models import Message, Session, SessionSummary


# ── Protocol (interface) ──────────────────────────────────────────────────

@runtime_checkable
class SessionStore(Protocol):
    """Interface for session storage backends."""

    def list_sessions(
        self, tenant_id: str, count: int = 10, page: int = 1
    ) -> list[SessionSummary]: ...

    def get_session(
        self, tenant_id: str, session_id: str
    ) -> Session | None: ...

    def create_session(
        self, tenant_id: str, user_id: str, label: str | None = None
    ) -> str: ...

    def delete_session(
        self, tenant_id: str, session_id: str
    ) -> bool: ...

    def update_session_label(
        self, tenant_id: str, session_id: str, label: str
    ) -> bool: ...

    def append_message(
        self, tenant_id: str, session_id: str, message: Message
    ) -> bool: ...


# ── In-memory implementation ──────────────────────────────────────────────

class InMemorySessionStore:
    """Dict-backed session store — suitable for development and testing."""

    def __init__(self) -> None:
        """Initialise an empty in-memory session store."""
        # Key: (tenant_id, session_id)  →  Session
        self._sessions: dict[tuple[str, str], Session] = {}

    def list_sessions(
        self, tenant_id: str, count: int = 10, page: int = 1
    ) -> list[SessionSummary]:
        """Return a paginated list of session summaries for a tenant."""
        tenant_sessions = sorted(
            (s for s in self._sessions.values() if s.tenant_id == tenant_id),
            key=lambda s: s.updated_at,
            reverse=True,
        )
        start = (page - 1) * count
        end = start + count
        return [
            SessionSummary(
                session_id=s.session_id,
                tenant_id=s.tenant_id,
                user_id=s.user_id,
                label=s.label,
                message_count=len(s.messages),
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in tenant_sessions[start:end]
        ]

    def get_session(
        self, tenant_id: str, session_id: str
    ) -> Session | None:
        """Return a full session with message history, or None."""
        return self._sessions.get((tenant_id, session_id))

    def create_session(
        self, tenant_id: str, user_id: str, label: str | None = None
    ) -> str:
        """Create a new session and return its ID."""
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        effective_label = label or now.strftime("%Y-%m-%d %H:%M")
        session = Session(
            session_id=session_id,
            tenant_id=tenant_id,
            user_id=user_id,
            label=effective_label,
            messages=[],
            created_at=now,
            updated_at=now,
        )
        self._sessions[(tenant_id, session_id)] = session
        return session_id

    def delete_session(
        self, tenant_id: str, session_id: str
    ) -> bool:
        """Delete a session. Returns True if it existed."""
        key = (tenant_id, session_id)
        if key in self._sessions:
            del self._sessions[key]
            return True
        return False

    def update_session_label(
        self, tenant_id: str, session_id: str, label: str
    ) -> bool:
        """Update a session's label. Returns True if found."""
        session = self._sessions.get((tenant_id, session_id))
        if session is None:
            return False
        session.label = label
        session.updated_at = datetime.now(timezone.utc)
        return True

    def append_message(
        self, tenant_id: str, session_id: str, message: Message
    ) -> bool:
        """Append a message to a session. Returns True if found."""
        session = self._sessions.get((tenant_id, session_id))
        if session is None:
            return False
        session.messages.append(message)
        session.updated_at = datetime.now(timezone.utc)
        return True
