"""
API Routes — Auth, Chat (streaming), Revision, Publish, Sessions.
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sse_starlette.sse import EventSourceResponse

from app.core.auth import (
    create_access_token,
    get_current_user,
    get_password_hash,
    verify_password,
)
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    SessionResponse,
    Token,
    User,
    UserCreate,
)
from app.agents.orchestrator import run_orchestrator, run_revision
from app.agents.publisher import run_publisher
from app.services.session import session_manager

logger = logging.getLogger(__name__)
router = APIRouter()
_users_db: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@router.post("/auth/register", response_model=User)
async def register(user: UserCreate):
    if user.email in _users_db:
        raise HTTPException(status_code=400, detail="Email already registered")
    uid = str(uuid.uuid4())
    _users_db[user.email] = {
        "id": uid,
        "email": user.email,
        "username": user.username,
        "hashed_password": get_password_hash(user.password),
    }
    return User(id=uid, email=user.email, username=user.username)


@router.post("/auth/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = _users_db.get(form_data.username)
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=create_access_token(data={"sub": user["id"]}), token_type="bearer")


# ---------------------------------------------------------------------------
# Chat (streaming)
# ---------------------------------------------------------------------------


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest, user_id: str = Depends(get_current_user)):
    sid = request.session_id
    if not sid or not session_manager.get_session(sid):
        sid = session_manager.create_session(user_id).session_id
    session_manager.add_message(sid, "user", request.message)

    # Revision or new?
    existing = session_manager.get_last_result(sid)
    is_revision = bool(existing and existing.get("blog_content"))

    q: queue.Queue = queue.Queue()

    def cb(event: dict):
        q.put(event)

    def run():
        try:
            if is_revision:
                r = run_revision(
                    existing["blog_content"], existing.get("blog_title", ""), request.message, cb
                )
                existing.update(r)
                q.put({"type": "done", "data": existing})
            else:
                r = run_orchestrator(
                    request.message, word_count=request.word_count, status_callback=cb
                )
                q.put({"type": "done", "data": r})
        except Exception as exc:
            logger.error("Pipeline: %s", exc)
            q.put({"type": "error", "error": str(exc)})

    async def gen():
        threading.Thread(target=run, daemon=True).start()

        while True:
            try:
                msg = q.get(timeout=0.5)
            except queue.Empty:
                await asyncio.sleep(0.05)
                continue

            if msg.get("type") == "done":
                result = msg["data"]

                # Use humanized content if available, otherwise fall back to blog_content
                content = result.get("humanized_content", result.get("blog_content", ""))

                if content:
                    yield {
                        "event": "blog_start",
                        "data": json.dumps(
                            {
                                "title": result.get("blog_title", ""),
                                "word_count": result.get("blog_word_count", 0),
                            }
                        ),
                    }
                    words = content.split(" ")
                    for i, w in enumerate(words):
                        yield {
                            "event": "token",
                            "data": json.dumps({"token": w if i == 0 else f" {w}"}),
                        }
                        await asyncio.sleep(0.01)

                yield {
                    "event": "done",
                    "data": json.dumps(
                        {
                            "session_id": sid,
                            "can_publish": bool(content),
                            "is_revision": is_revision,
                        }
                    ),
                }

                formatted = _fmt(result)
                session_manager.add_message(sid, "assistant", formatted)
                session_manager.set_last_result(sid, result)
                break

            if msg.get("type") == "error":
                yield {"event": "error", "data": json.dumps({"error": msg["error"]})}
                session_manager.add_message(sid, "assistant", f"**Error:** {msg['error']}")
                break

            # Agent status / output
            if msg.get("status") == "running":
                yield {
                    "event": "status",
                    "data": json.dumps({"step": msg["step"], "status": "running"}),
                }
            elif msg.get("status") == "done":
                yield {
                    "event": "agent_output",
                    "data": json.dumps(
                        {
                            "step": msg["step"],
                            "title": msg.get("title", msg["step"]),
                            "output": msg.get("output", ""),
                        }
                    ),
                }

    return EventSourceResponse(gen())


# ---------------------------------------------------------------------------
# Chat (non-streaming)
# ---------------------------------------------------------------------------


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, user_id: str = Depends(get_current_user)):
    sid = request.session_id
    if not sid or not session_manager.get_session(sid):
        sid = session_manager.create_session(user_id).session_id
    session_manager.add_message(sid, "user", request.message)

    existing = session_manager.get_last_result(sid)
    is_revision = bool(existing and existing.get("blog_content"))

    try:
        if is_revision:
            r = await asyncio.to_thread(
                run_revision,
                existing["blog_content"],
                existing.get("blog_title", ""),
                request.message,
            )
            existing.update(r)
            result = existing
        else:
            result = await asyncio.to_thread(
                run_orchestrator, request.message, word_count=request.word_count
            )
    except Exception as exc:
        err = f"**Error:** {exc}"
        session_manager.add_message(sid, "assistant", err)
        return ChatResponse(session_id=sid, message=err, agent="orchestrator")

    formatted = _fmt(result)
    session_manager.add_message(sid, "assistant", formatted)
    session_manager.set_last_result(sid, result)
    return ChatResponse(session_id=sid, message=formatted, agent="orchestrator")


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------


@router.post("/chat/publish")
async def publish_blog(request: ChatRequest, user_id: str = Depends(get_current_user)):
    sid = request.session_id
    if not sid:
        raise HTTPException(400, "session_id required")
    if not session_manager.get_session(sid):
        raise HTTPException(404, "Session not found")
    last = session_manager.get_last_result(sid)
    if not last or not last.get("humanized_content"):
        raise HTTPException(400, "No blog content in session")

    content = last.get("humanized_content", last.get("blog_content", ""))
    r = await asyncio.to_thread(
        run_publisher,
        title=last.get("blog_title", "Untitled"),
        content=content,
        excerpt=last.get("seo_meta", ""),
        status="draft",
    )
    return {
        "success": r.get("success", False),
        "post_id": r.get("post_id"),
        "permalink": r.get("permalink"),
        "error": r.get("error"),
    }


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(user_id: str = Depends(get_current_user)):
    return session_manager.list_sessions(user_id)


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, user_id: str = Depends(get_current_user)):
    s = session_manager.get_session(session_id)
    if not s:
        raise HTTPException(404, "Not found")
    if s.user_id != user_id:
        raise HTTPException(403)
    return s


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, user_id: str = Depends(get_current_user)):
    s = session_manager.get_session(session_id)
    if not s:
        raise HTTPException(404, "Not found")
    if s.user_id != user_id:
        raise HTTPException(403)
    session_manager.delete_session(session_id)
    return {"detail": "Deleted"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt(r: dict) -> str:
    content = r.get("humanized_content", r.get("blog_content", ""))
    parts = []
    if content:
        parts.append(f"## 📝 {r.get('blog_title', '')}\n\n{content}")
    if r.get("keywords"):
        parts.append(f"\n**Keywords:** {', '.join(r.get('keywords', []))}")
    return "\n\n".join(parts) or "No output."
