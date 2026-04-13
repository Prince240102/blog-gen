"""
In-memory session manager.

Each session stores the full message history and a summary of the last
orchestrator run so the user can reference previous work in follow-up
messages.

For production you'd swap this for Redis / Postgres / etc.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional

from app.models.schemas import SessionResponse


class SessionManager:
    def __init__(self) -> None:
        self._sessions: Dict[str, dict] = {}

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_session(self, user_id: str) -> SessionResponse:
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        session = {
            "session_id": session_id,
            "user_id": user_id,
            "messages": [],
            "last_result": None,
            "created_at": now,
        }
        self._sessions[session_id] = session
        return SessionResponse(**session)

    def get_session(self, session_id: str) -> Optional[SessionResponse]:
        data = self._sessions.get(session_id)
        if data is None:
            return None
        return SessionResponse(**data)

    def delete_session(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def add_message(self, session_id: str, role: str, content: str) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        session["messages"].append(
            {
                "role": role,
                "content": content,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def get_messages(self, session_id: str, limit: int = 20) -> list[dict]:
        session = self._sessions.get(session_id)
        if session is None:
            return []
        return session["messages"][-limit:]

    # ------------------------------------------------------------------
    # Context helpers
    # ------------------------------------------------------------------

    def get_context_string(self, session_id: str, limit: int = 10) -> str:
        """Return a condensed string of recent messages for LLM context."""
        messages = self.get_messages(session_id, limit=limit)
        parts: list[str] = []
        for msg in messages:
            role = msg["role"].capitalize()
            # Truncate very long messages in context
            content = msg["content"][:3000]
            parts.append(f"{role}: {content}")
        return "\n\n".join(parts)

    def set_last_result(self, session_id: str, result: dict) -> None:
        session = self._sessions.get(session_id)
        if session is not None:
            session["last_result"] = result

    def get_last_result(self, session_id: str) -> Optional[dict]:
        session = self._sessions.get(session_id)
        if session is not None:
            return session.get("last_result")
        return None

    def list_sessions(self, user_id: str) -> list[SessionResponse]:
        return [
            SessionResponse(**s)
            for s in self._sessions.values()
            if s["user_id"] == user_id
        ]


session_manager = SessionManager()
