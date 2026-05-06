"""
SQLite-backed store for users, sessions, and messages.

Replaces the in-memory dicts. The database file lives at /app/data/blogforge.db
inside the container, backed by a Docker volume so data survives restarts.

Uses a single connection with `check_same_thread=False` and wraps all
writes in a thread lock. Good enough for single-container deployments.
For multi-replica setups swap this for Postgres.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.core.auth import get_password_hash, verify_password
from app.models.schemas import SessionResponse, User

DB_DIR = Path("/app/data")
DB_PATH = DB_DIR / "blogforge.db"

_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_DIR.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
        _migrate(_conn)
    return _conn


def _migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id          TEXT PRIMARY KEY,
            email       TEXT UNIQUE NOT NULL,
            username    TEXT NOT NULL,
            hashed_password TEXT NOT NULL,
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            session_id  TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
            role        TEXT NOT NULL,
            content     TEXT NOT NULL,
            timestamp   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS blog_drafts (
            session_id  TEXT PRIMARY KEY REFERENCES sessions(session_id) ON DELETE CASCADE,
            title       TEXT NOT NULL DEFAULT '',
            content     TEXT NOT NULL DEFAULT '',
            word_count  INTEGER NOT NULL DEFAULT 0,
            keywords    TEXT NOT NULL DEFAULT '',
            meta_description TEXT NOT NULL DEFAULT '',
            post_id     INTEGER NOT NULL DEFAULT 0,
            permalink   TEXT NOT NULL DEFAULT '',
            updated_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS blog_versions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
            version     INTEGER NOT NULL DEFAULT 1,
            title       TEXT NOT NULL DEFAULT '',
            content     TEXT NOT NULL DEFAULT '',
            word_count  INTEGER NOT NULL DEFAULT 0,
            keywords    TEXT NOT NULL DEFAULT '',
            meta_description TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL,
            UNIQUE(session_id, version)
        );

        CREATE TABLE IF NOT EXISTS tool_steps (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
            turn_id     INTEGER NOT NULL,
            seq         INTEGER NOT NULL,
            tool        TEXT NOT NULL,
            label       TEXT NOT NULL DEFAULT '',
            icon        TEXT NOT NULL DEFAULT '',
            status      TEXT NOT NULL DEFAULT 'running',
            progress    TEXT NOT NULL DEFAULT '',
            output      TEXT NOT NULL DEFAULT '',
            started_at  TEXT NOT NULL,
            ended_at    TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_tool_steps_session
            ON tool_steps(session_id, id);
        CREATE INDEX IF NOT EXISTS idx_tool_steps_turn
            ON tool_steps(session_id, turn_id, seq);

        CREATE INDEX IF NOT EXISTS idx_messages_session
            ON messages(session_id, id);
        CREATE INDEX IF NOT EXISTS idx_sessions_user
            ON sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_versions_session
            ON blog_versions(session_id, version);
        """
    )
    # Add columns to existing blog_drafts table if missing
    try:
        conn.execute("ALTER TABLE blog_drafts ADD COLUMN keywords TEXT NOT NULL DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE blog_drafts ADD COLUMN meta_description TEXT NOT NULL DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE blog_drafts ADD COLUMN published INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE blog_drafts ADD COLUMN current_version INTEGER NOT NULL DEFAULT 1")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE blog_drafts ADD COLUMN post_id INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE blog_drafts ADD COLUMN permalink TEXT NOT NULL DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE messages ADD COLUMN summary TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()


# ===================================================================
# Users
# ===================================================================


def create_user(email: str, username: str, password: str) -> User:
    uid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    hashed = get_password_hash(password)
    with _lock:
        _get_conn().execute(
            "INSERT INTO users (id, email, username, hashed_password, created_at) VALUES (?,?,?,?,?)",
            (uid, email, username, hashed, now),
        )
        _get_conn().commit()
    return User(id=uid, email=email, username=username, created_at=now)


def get_user_by_email(email: str) -> Optional[dict]:
    row = _get_conn().execute(
        "SELECT * FROM users WHERE email = ?", (email,)
    ).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: str) -> Optional[dict]:
    row = _get_conn().execute(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    return dict(row) if row else None


def authenticate_user(email: str, password: str) -> Optional[dict]:
    user = get_user_by_email(email)
    if not user:
        return None
    if not verify_password(password, user["hashed_password"]):
        return None
    return user


# ===================================================================
# Sessions
# ===================================================================


def create_session(user_id: str) -> SessionResponse:
    sid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        _get_conn().execute(
            "INSERT INTO sessions (session_id, user_id, created_at) VALUES (?,?,?)",
            (sid, user_id, now),
        )
        _get_conn().commit()
    return SessionResponse(session_id=sid, user_id=user_id, created_at=now)


def get_session(session_id: str) -> Optional[SessionResponse]:
    row = _get_conn().execute(
        "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if not row:
        return None
    msgs = get_messages(session_id, limit=None)
    draft = get_draft(session_id)
    published = draft.get("published", False) if draft else False
    permalink = draft.get("permalink") if draft else None
    return SessionResponse(
        session_id=row["session_id"],
        user_id=row["user_id"],
        messages=msgs,
        created_at=row["created_at"],
        has_draft=draft is not None and bool(draft.get("humanized_content")) and not published,
        is_published=published,
        permalink=permalink,
    )


def delete_session(session_id: str) -> bool:
    with _lock:
        cursor = _get_conn().execute(
            "DELETE FROM sessions WHERE session_id = ?", (session_id,)
        )
        _get_conn().commit()
        return cursor.rowcount > 0


def list_sessions(user_id: str) -> list[SessionResponse]:
    rows = _get_conn().execute(
        "SELECT * FROM sessions WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    result = []
    for row in rows:
        msgs = get_recent_messages(row["session_id"], limit=5)
        draft = get_draft(row["session_id"])
        published = draft.get("published", False) if draft else False
        permalink = draft.get("permalink") if draft else None
        result.append(
            SessionResponse(
                session_id=row["session_id"],
                user_id=row["user_id"],
                messages=msgs,
                created_at=row["created_at"],
                has_draft=draft is not None and bool(draft.get("humanized_content")) and not published,
                is_published=published,
                permalink=permalink,
            )
        )
    return result


# ===================================================================
# Messages
# ===================================================================


def add_message(session_id: str, role: str, content: str, summary: str = "") -> int:
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        cur = _get_conn().execute(
            "INSERT INTO messages (session_id, role, content, timestamp, summary) VALUES (?,?,?,?,?)",
            (session_id, role, content, now, summary or None),
        )
        _get_conn().commit()
        return int(cur.lastrowid)


def start_tool_step(session_id: str, turn_id: int, seq: int, tool: str, label: str = "", icon: str = "") -> int:
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        cur = _get_conn().execute(
            "INSERT INTO tool_steps (session_id, turn_id, seq, tool, label, icon, status, started_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (session_id, turn_id, seq, tool, label, icon, "running", now),
        )
        _get_conn().commit()
        return int(cur.lastrowid)


def update_tool_step_progress(step_id: int, progress: str) -> None:
    with _lock:
        _get_conn().execute(
            "UPDATE tool_steps SET progress = ? WHERE id = ?",
            (progress[:2000], step_id),
        )
        _get_conn().commit()


def finish_tool_step(step_id: int, status: str, output: str = "") -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        _get_conn().execute(
            "UPDATE tool_steps SET status = ?, output = ?, ended_at = ? WHERE id = ?",
            (status, (output or "")[:8000], now, step_id),
        )
        _get_conn().commit()


def list_tool_steps(session_id: str, limit: int = 50) -> list[dict]:
    rows = _get_conn().execute(
        "SELECT id, turn_id, seq, tool, label, icon, status, progress, output, started_at, ended_at "
        "FROM tool_steps WHERE session_id = ? ORDER BY id DESC LIMIT ?",
        (session_id, limit),
    ).fetchall()
    return list(reversed([dict(r) for r in rows]))


def update_message_summary(msg_id: int, summary: str) -> None:
    with _lock:
        _get_conn().execute(
            "UPDATE messages SET summary = ? WHERE id = ?",
            (summary, msg_id),
        )
        _get_conn().commit()


def get_messages(session_id: str, limit: Optional[int] = 20) -> list[dict]:
    if limit is None:
        rows = _get_conn().execute(
            "SELECT id, role, content, timestamp, summary FROM messages "
            "WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
    else:
        rows = _get_conn().execute(
            "SELECT id, role, content, timestamp, summary FROM messages "
            "WHERE session_id = ? ORDER BY id ASC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_recent_messages(session_id: str, limit: int = 20) -> list[dict]:
    """Get the last N messages — uses a subquery to grab the tail."""
    rows = _get_conn().execute(
        "SELECT id, role, content, timestamp, summary FROM messages "
        "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
        (session_id, limit),
    ).fetchall()
    return list(reversed([dict(r) for r in rows]))


# ===================================================================
# Blog Drafts
# ===================================================================


def set_draft(session_id: str, title: str, content: str, word_count: int,
              keywords: str = "", meta_description: str = "",
              post_id: int = 0, permalink: str = "", create_version: bool = True) -> None:
    """Save draft. If create_version=True and overwriting an existing draft, archive the old one first."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()

    with _lock:
        # Check if there's an existing draft to archive (only if create_version=True)
        existing = conn.execute(
            "SELECT title, content, word_count, keywords, meta_description, current_version "
            "FROM blog_drafts WHERE session_id = ?",
            (session_id,),
        ).fetchone()

        if create_version and existing and existing["content"].strip():
            # Archive the old version
            old_ver = existing["current_version"]
            conn.execute(
                "INSERT OR IGNORE INTO blog_versions "
                "(session_id, version, title, content, word_count, keywords, meta_description, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (session_id, old_ver, existing["title"], existing["content"],
                 existing["word_count"], existing["keywords"], existing["meta_description"], now),
            )
            new_ver = old_ver + 1
        elif existing:
            new_ver = existing["current_version"]
        else:
            new_ver = 1

        conn.execute(
            "INSERT INTO blog_drafts "
            "(session_id, title, content, word_count, keywords, meta_description, post_id, permalink, published, current_version, updated_at) "
            "VALUES (?,?,?,?,?,?,?, ?,0,?,?) "
            "ON CONFLICT(session_id) DO UPDATE SET "
            "title=?, content=?, word_count=?, keywords=?, meta_description=?, "
            "post_id=?, permalink=?, published=0, current_version=?, updated_at=?",
            (session_id, title, content, word_count, keywords, meta_description, post_id, permalink, new_ver, now,
             title, content, word_count, keywords, meta_description, post_id, permalink, new_ver, now),
        )
        conn.commit()


def get_draft(session_id: str) -> Optional[dict]:
    row = _get_conn().execute(
        "SELECT title, content, word_count, keywords, meta_description, post_id, permalink, published, current_version, updated_at "
        "FROM blog_drafts WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "blog_title": row["title"],
        "humanized_content": row["content"],
        "blog_content": row["content"],
        "blog_word_count": row["word_count"],
        "keywords": row["keywords"],
        "meta_description": row["meta_description"],
        "post_id": row["post_id"],
        "permalink": row["permalink"],
        "published": bool(row["published"]),
        "current_version": row["current_version"],
    }


def mark_published(session_id: str, post_id: int, permalink: str) -> None:
    """Mark a draft as published so the publish button stops showing."""
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        _get_conn().execute(
            "UPDATE blog_drafts SET published=1, post_id=?, permalink=?, updated_at=? WHERE session_id=?",
            (post_id, permalink, now, session_id),
        )
        _get_conn().commit()


def list_versions(session_id: str) -> list[dict]:
    """Return all archived versions plus the current draft as the latest version."""
    rows = _get_conn().execute(
        "SELECT version, title, word_count, keywords, meta_description, created_at "
        "FROM blog_versions WHERE session_id = ? ORDER BY version ASC",
        (session_id,),
    ).fetchall()

    versions = []
    for r in rows:
        versions.append({
            "version": r["version"],
            "title": r["title"],
            "word_count": r["word_count"],
            "keywords": r["keywords"],
            "meta_description": r["meta_description"],
            "created_at": r["created_at"],
            "is_current": False,
        })

    # Append the current draft as the latest version
    draft = get_draft(session_id)
    if draft and draft.get("humanized_content"):
        versions.append({
            "version": draft.get("current_version", len(versions) + 1),
            "title": draft["blog_title"],
            "word_count": draft["blog_word_count"],
            "keywords": draft["keywords"],
            "meta_description": draft["meta_description"],
            "created_at": "",
            "is_current": True,
        })

    return versions


def get_version(session_id: str, version: int) -> Optional[dict]:
    """Get a specific version. Returns the current draft if version matches."""
    draft = get_draft(session_id)
    if draft and draft.get("current_version") == version:
        return draft

    row = _get_conn().execute(
        "SELECT version, title, content, word_count, keywords, meta_description, created_at "
        "FROM blog_versions WHERE session_id = ? AND version = ?",
        (session_id, version),
    ).fetchone()
    if not row:
        return None
    return {
        "blog_title": row["title"],
        "humanized_content": row["content"],
        "blog_content": row["content"],
        "blog_word_count": row["word_count"],
        "keywords": row["keywords"],
        "meta_description": row["meta_description"],
        "version": row["version"],
        "created_at": row["created_at"],
        "is_current": False,
    }


def restore_version(session_id: str, version: int) -> Optional[dict]:
    """Restore an old version as the new current draft. Returns the restored draft."""
    ver = get_version(session_id, version)
    if not ver:
        return None
    # set_draft will archive the current draft and write this as new version
    set_draft(
        session_id,
        title=ver["blog_title"],
        content=ver["humanized_content"],
        word_count=ver["blog_word_count"],
        keywords=ver.get("keywords", ""),
        meta_description=ver.get("meta_description", ""),
    )
    return get_draft(session_id)
