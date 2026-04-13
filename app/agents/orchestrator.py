"""
Orchestrator Agent
------------------
Pipeline: Research → SEO → Content → Humanize → Show for approval → Publish

Each step streams its output so the user can see what's happening.
"""

from __future__ import annotations

import logging
import re
from typing import Callable, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.content import run_content_generator
from app.agents.humanize import run_humanize
from app.agents.research import run_research
from app.agents.seo import run_seo
from app.services.llm import llm

logger = logging.getLogger(__name__)


def _emit(callback, event: dict):
    if callback:
        try:
            callback(event)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------


def run_orchestrator(
    user_request: str,
    word_count: int = 1500,
    topic: str = "",
    status_callback: Optional[Callable] = None,
) -> dict:
    topic = topic or user_request

    result = {
        "topic": topic,
        "research_analysis": "",
        "keywords": [],
        "seo_meta": "",
        "seo_score": 0,
        "seo_suggestions": [],
        "blog_title": "",
        "blog_content": "",
        "humanized_content": "",
        "blog_word_count": 0,
    }

    # 1. Research
    _emit(status_callback, {"step": "research", "status": "running"})
    try:
        r = run_research(topic)
        result["research_analysis"] = r["analysis"]
        _emit(
            status_callback,
            {
                "step": "research",
                "status": "done",
                "title": "Research Findings",
                "output": r["analysis"][:3000],
            },
        )
    except Exception as exc:
        logger.warning("Research failed: %s", exc)
        _emit(
            status_callback,
            {
                "step": "research",
                "status": "done",
                "title": "Research",
                "output": f"Skipped — {exc}",
            },
        )

    # 2. SEO
    _emit(status_callback, {"step": "seo", "status": "running"})
    try:
        r = run_seo(topic=topic, research=result["research_analysis"])
        result["keywords"] = r["keywords"]
        result["seo_meta"] = r["meta_description"]
        result["seo_score"] = r.get("seo_score", 0)
        result["seo_suggestions"] = r.get("suggestions", [])
        seo_text = (
            f"**Meta description:** {r['meta_description']}\n\n"
            f"**Keywords:** {', '.join(r['keywords'])}\n\n"
        )
        _emit(
            status_callback,
            {
                "step": "seo",
                "status": "done",
                "title": "SEO Optimization Applied",
                "output": seo_text,
            },
        )
    except Exception as exc:
        logger.warning("SEO failed: %s", exc)
        _emit(
            status_callback,
            {
                "step": "seo",
                "status": "done",
                "title": "SEO",
                "output": f"Skipped — {exc}",
            },
        )

    # 3. Content
    _emit(status_callback, {"step": "content", "status": "running"})
    try:
        r = run_content_generator(
            topic=topic,
            research=result["research_analysis"],
            keywords=result["keywords"],
            word_count=word_count,
        )
        result["blog_title"] = r["title"]
        result["blog_content"] = r["content"]
        result["blog_word_count"] = r["word_count"]
        _emit(
            status_callback,
            {
                "step": "content",
                "status": "done",
                "title": r["title"],
                "output": r["content"],
                "word_count": r["word_count"],
            },
        )
    except Exception as exc:
        logger.error("Content failed: %s", exc)
        _emit(
            status_callback,
            {
                "step": "content",
                "status": "done",
                "title": "Content",
                "output": f"Failed — {exc}",
            },
        )
        raise

    # 4. Humanize
    _emit(status_callback, {"step": "humanize", "status": "running"})
    try:
        r = run_humanize(
            content=result["blog_content"],
            title=result["blog_title"],
        )
        result["humanized_content"] = r["content"]
        _emit(
            status_callback,
            {
                "step": "humanize",
                "status": "done",
                "title": "Humanized Content",
                "output": r["content"],
                "word_count": len(r["content"].split()),
            },
        )
    except Exception as exc:
        logger.warning("Humanize failed: %s", exc)
        result["humanized_content"] = result["blog_content"]

    return result


# ---------------------------------------------------------------------------
# Revision
# ---------------------------------------------------------------------------


def run_revision(
    current_content: str,
    current_title: str,
    feedback: str,
    status_callback: Optional[Callable] = None,
) -> dict:
    _emit(status_callback, {"step": "content", "status": "running"})

    system = (
        "You are an expert blog editor. The user has reviewed their blog post and "
        "given feedback. Revise the entire post to address it.\n\n"
        "Rules:\n"
        "- Keep structure unless asked to change\n"
        "- Preserve SEO keywords and Markdown formatting\n"
        "- Return the FULL revised post\n"
        "- Start with an H1 heading (title)"
    )

    human = (
        f"Current title: {current_title}\n\n"
        f"Current post:\n{current_content}\n\n"
        f"User feedback: {feedback}\n\n"
        "Write the revised blog post:"
    )

    resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=human)])
    new_content = resp.content
    m = re.search(r"^#\s+(.+)$", new_content, re.MULTILINE)
    new_title = m.group(1).strip() if m else current_title

    # Humanize the revised content
    _emit(status_callback, {"step": "humanize", "status": "running"})
    try:
        h = run_humanize(content=new_content, title=new_title)
        humanized = h["content"]
    except Exception:
        humanized = new_content

    _emit(
        status_callback,
        {
            "step": "content",
            "status": "done",
            "title": new_title,
            "output": humanized,
            "word_count": len(humanized.split()),
        },
    )

    return {
        "blog_title": new_title,
        "blog_content": new_content,
        "humanized_content": humanized,
        "blog_word_count": len(humanized.split()),
    }
