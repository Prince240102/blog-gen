"""
Progress Callback
-----------------
Thread-safe callback for streaming sub-agent progress to the frontend.
Tools call `progress.emit("Searching web...")` and the SSE stream
picks it up and forwards it as a step_progress event.

Uses a simple list with a lock so it's safe across threads
(the agent runs tools in a thread pool while the SSE loop is async).
"""

from __future__ import annotations

import threading
from typing import Optional


class ProgressCallback:
    """Collects progress messages from sub-agents during a request.

    The SSE streaming loop polls this after each tool event to emit
    step_progress events to the frontend.
    """

    def __init__(self) -> None:
        self._messages: list[str] = []
        self._lock = threading.Lock()

    def emit(self, message: str) -> None:
        with self._lock:
            self._messages.append(message)

    def drain(self) -> list[str]:
        """Return all pending progress messages and clear the buffer."""
        with self._lock:
            msgs = self._messages.copy()
            self._messages.clear()
            return msgs


# Module-level singleton — set per request by the SSE handler
_current: Optional[ProgressCallback] = None


def set_progress(cb: Optional[ProgressCallback]) -> None:
    global _current
    _current = cb


def get_progress() -> ProgressCallback:
    """Get the current request's progress callback. Returns a no-op if none set."""
    if _current is not None:
        return _current
    return _NOP


class _NoOpProgress:
    """Fallback that silently discards messages."""
    def emit(self, message: str) -> None:
        pass

    def drain(self) -> list[str]:
        return []


_NOP = _NoOpProgress()