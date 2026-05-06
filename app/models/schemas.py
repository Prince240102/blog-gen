from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str = Field(..., min_length=6)


class User(BaseModel):
    id: str
    email: str
    username: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    user_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    word_count: int = 1500


class ChatResponse(BaseModel):
    session_id: str
    message: str
    agent: str = "orchestrator"
    data: Optional[dict] = None


class SessionResponse(BaseModel):
    session_id: str
    user_id: str
    messages: list[dict] = Field(default_factory=list)
    created_at: Optional[str] = None
    has_draft: bool = False
    is_published: bool = False
    permalink: Optional[str] = None


# ---------------------------------------------------------------------------
# Agent intermediate schemas (internal use)
# ---------------------------------------------------------------------------

class ResearchOutput(BaseModel):
    query: str
    raw_results: str
    analysis: str


class SEOOutput(BaseModel):
    meta_description: str
    keywords: list[str]
    seo_score: int
    suggestions: list[str]
    optimized_content: str


class ContentOutput(BaseModel):
    title: str
    content: str
    word_count: int


class VlogOutput(BaseModel):
    video_script: str
    timestamps: list[dict]
    narrator_notes: str
    estimated_duration_minutes: int


class PublishOutput(BaseModel):
    success: bool
    post_id: Optional[int] = None
    permalink: Optional[str] = None
    error: Optional[str] = None
