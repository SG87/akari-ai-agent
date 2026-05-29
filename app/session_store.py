"""
Session store with a protocol-based interface for easy swapping.

Backends:
  - InMemorySessionStore: dict-backed, suitable for development and testing.
  - CosmosSessionStore:   Azure Cosmos DB NoSQL, persistent and production-ready.

Toggle via the SESSION_STORE_BACKEND setting ("memory" or "cosmos").
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from app.models import Message, Session, SessionSummary

logger = logging.getLogger("akari.session_store")


# ── Protocol (interface) ──────────────────────────────────────────────────

@runtime_checkable
class SessionStore(Protocol):
    """Interface for session storage backends."""

    def list_sessions(
        self, tenant_id: str, user_id: str, count: int = 10, page: int = 1
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
        self, tenant_id: str, user_id: str, count: int = 10, page: int = 1
    ) -> list[SessionSummary]:
        """Return a paginated list of session summaries for a tenant and user."""
        tenant_sessions = sorted(
            (s for s in self._sessions.values()
             if s.tenant_id == tenant_id and s.user_id == user_id),
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


# ── Cosmos DB implementation ──────────────────────────────────────────────

class CosmosSessionStore:
    """Azure Cosmos DB–backed session store — persistent and production-ready.

    Document schema:
        {
            "id":        "<session_id>",       # Cosmos document ID
            "tenantId":  "<tenant_id>",        # Partition key
            "userId":    "<user_id>",
            "label":     "...",
            "messages":  [ { persona, message, timestamp, metadata }, ... ],
            "createdAt": "2026-05-29T12:00:00Z",
            "updatedAt": "2026-05-29T12:00:00Z"
        }
    """

    def __init__(self) -> None:
        """Connect to Cosmos DB using settings from config."""
        from azure.cosmos import CosmosClient, PartitionKey
        from azure.cosmos.exceptions import CosmosResourceNotFoundError
        from app.config import settings

        self._not_found_error = CosmosResourceNotFoundError

        if not settings.COSMOS_ENDPOINT or not settings.COSMOS_KEY:
            raise ValueError(
                "Cosmos DB credentials not configured. "
                "Set COSMOS_ENDPOINT and COSMOS_KEY in your .env file."
            )

        client = CosmosClient(settings.COSMOS_ENDPOINT, settings.COSMOS_KEY)

        # Create database and container if they don't exist
        self._database = client.create_database_if_not_exists(
            id=settings.COSMOS_DATABASE
        )
        self._container = self._database.create_container_if_not_exists(
            id=settings.COSMOS_CONTAINER,
            partition_key=PartitionKey(path="/tenantId"),
        )
        logger.info(
            "✅ Cosmos DB session store connected: %s/%s",
            settings.COSMOS_DATABASE,
            settings.COSMOS_CONTAINER,
        )

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _doc_to_session(doc: dict) -> Session:
        """Convert a Cosmos DB document to a Session model."""
        messages = [
            Message(
                persona=m["persona"],
                message=m["message"],
                timestamp=m["timestamp"],
                metadata=m.get("metadata"),
            )
            for m in doc.get("messages", [])
        ]
        return Session(
            session_id=doc["id"],
            tenant_id=doc["tenantId"],
            user_id=doc["userId"],
            label=doc.get("label", ""),
            messages=messages,
            created_at=doc["createdAt"],
            updated_at=doc["updatedAt"],
        )

    @staticmethod
    def _doc_to_summary(doc: dict) -> SessionSummary:
        """Convert a Cosmos DB query result to a SessionSummary."""
        return SessionSummary(
            session_id=doc["id"],
            tenant_id=doc["tenantId"],
            user_id=doc["userId"],
            label=doc.get("label", ""),
            message_count=doc.get("messageCount", 0),
            created_at=doc["createdAt"],
            updated_at=doc["updatedAt"],
        )

    # ── Protocol methods ───────────────────────────────────────────────

    def list_sessions(
        self, tenant_id: str, user_id: str, count: int = 10, page: int = 1
    ) -> list[SessionSummary]:
        """Return a paginated list of session summaries for a tenant and user."""
        offset = (page - 1) * count
        query = (
            "SELECT c.id, c.tenantId, c.userId, c.label, "
            "ARRAY_LENGTH(c.messages) AS messageCount, "
            "c.createdAt, c.updatedAt "
            "FROM c "
            "WHERE c.userId = @userId "
            "ORDER BY c.updatedAt DESC "
            "OFFSET @offset LIMIT @limit"
        )
        parameters = [
            {"name": "@userId", "value": user_id},
            {"name": "@offset", "value": offset},
            {"name": "@limit", "value": count},
        ]
        items = list(
            self._container.query_items(
                query=query,
                parameters=parameters,
                partition_key=tenant_id,
            )
        )
        return [self._doc_to_summary(item) for item in items]

    def get_session(
        self, tenant_id: str, session_id: str
    ) -> Session | None:
        """Point-read a session document (~1 RU)."""
        try:
            doc = self._container.read_item(
                item=session_id,
                partition_key=tenant_id,
            )
            return self._doc_to_session(doc)
        except self._not_found_error:
            return None

    def create_session(
        self, tenant_id: str, user_id: str, label: str | None = None
    ) -> str:
        """Create a new session document and return its ID."""
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        effective_label = label or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

        doc = {
            "id": session_id,
            "tenantId": tenant_id,
            "userId": user_id,
            "label": effective_label,
            "messages": [],
            "createdAt": now,
            "updatedAt": now,
        }
        self._container.create_item(body=doc)
        return session_id

    def delete_session(
        self, tenant_id: str, session_id: str
    ) -> bool:
        """Delete a session document. Returns True if it existed."""
        try:
            self._container.delete_item(
                item=session_id,
                partition_key=tenant_id,
            )
            return True
        except self._not_found_error:
            return False

    def update_session_label(
        self, tenant_id: str, session_id: str, label: str
    ) -> bool:
        """Patch a session's label and updatedAt timestamp."""
        now = datetime.now(timezone.utc).isoformat()
        try:
            self._container.patch_item(
                item=session_id,
                partition_key=tenant_id,
                patch_operations=[
                    {"op": "set", "path": "/label", "value": label},
                    {"op": "set", "path": "/updatedAt", "value": now},
                ],
            )
            return True
        except self._not_found_error:
            return False

    def append_message(
        self, tenant_id: str, session_id: str, message: Message
    ) -> bool:
        """Append a message to the messages array via patch."""
        now = datetime.now(timezone.utc).isoformat()
        msg_dict = {
            "persona": message.persona,
            "message": message.message,
            "timestamp": message.timestamp.isoformat(),
            "metadata": message.metadata,
        }
        try:
            self._container.patch_item(
                item=session_id,
                partition_key=tenant_id,
                patch_operations=[
                    {"op": "add", "path": "/messages/-", "value": msg_dict},
                    {"op": "set", "path": "/updatedAt", "value": now},
                ],
            )
            return True
        except self._not_found_error:
            return False


# ── Factory ───────────────────────────────────────────────────────────────

def create_session_store(backend: str = "memory") -> SessionStore:
    """Create a session store instance based on the configured backend.

    Args:
        backend: "memory" for InMemorySessionStore, "cosmos" for CosmosSessionStore.

    Returns:
        A SessionStore implementation.
    """
    if backend == "cosmos":
        logger.info("Initialising Cosmos DB session store...")
        return CosmosSessionStore()

    logger.info("Using in-memory session store (data will not persist across restarts)")
    return InMemorySessionStore()

