"""
Agent Tools
-----------
Tools the ReAct agent can call. Each sub-agent is wrapped as a @tool
so the main agent decides when to use them.

Tools that need the current draft can read it from the store using session_id,
instead of requiring the full content as an argument.
"""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

from app.agents.research import run_research
from app.agents.content import run_content_generator
from app.agents.humanize import run_humanize
from app.agents.publisher import run_publisher
from app.agents.seo import run_seo
from app.agents.vlog import run_vlog_editor
from app.services import store as store_module
from app.services.llm import llm
from app.services.progress import get_progress
import httpx

from app.core.config import settings


def _get_draft_content(session_id: str, fallback_content: str) -> str:
    """Read draft from store if available, otherwise use provided content."""
    if session_id:
        draft = store_module.get_draft(session_id)
        if draft and draft.get("humanized_content"):
            return draft["humanized_content"]
    return fallback_content


# ---------------------------------------------------------------------------
# Web Search
# ---------------------------------------------------------------------------


@tool
def web_search(query: str) -> str:
    """Search the web for quick facts, current info, or to answer questions.
    Returns the top search results with titles, URLs, and descriptions."""
    api_key = settings.brave_api_key
    if not api_key:
        return "Search unavailable: Brave API key not configured."

    try:
        resp = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": 8, "text_decorations": False},
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": api_key,
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get("web", {}).get("results", []):
            results.append(
                f"- **{item.get('title', '')}**\n  {item.get('description', '')}\n  {item.get('url', '')}"
            )

        return "\n\n".join(results) if results else "No results found."
    except Exception as exc:
        return f"Search error: {exc}"


# ---------------------------------------------------------------------------
# Research sub-agent
# ---------------------------------------------------------------------------


@tool
def research_topic(query: str) -> str:
    """Run a deep research sub-agent on a topic. Searches the web, analyzes
    results, and returns a structured brief with key findings, angles,
    a suggested outline, and source URLs. Always use this before writing
    a blog post to ensure well-informed content."""
    get_progress().emit("Starting research…")
    result = run_research(query)
    return result["analysis"]


# ---------------------------------------------------------------------------
# SEO sub-agent
# ---------------------------------------------------------------------------


@tool
def analyze_seo(topic: str, research_brief: str) -> str:
    """Get target keywords and a meta description for a blog post.
    Returns JSON with keywords and meta_description."""
    get_progress().emit("Analyzing SEO…")
    result = run_seo(topic=topic, research=research_brief)
    return json.dumps(
        {
            "keywords": result["keywords"],
            "meta_description": result["meta_description"],
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Content sub-agent
# ---------------------------------------------------------------------------


@tool
def write_blog(
    topic: str,
    research_brief: str = "",
    keywords: str = "",
    word_count: int = 1500,
) -> str:
    """Generate a full SEO-optimized blog post in Markdown.

    Args:
        topic: The blog topic or title.
        research_brief: Output from the research_topic tool.
        keywords: Comma-separated target keywords.
        word_count: Target word count (default 1500).
    """
    get_progress().emit(f"Writing {word_count}-word blog post…")
    kw_list = [k.strip() for k in keywords.split(",") if k.strip()] if keywords else []
    result = run_content_generator(
        topic=topic,
        research=research_brief,
        keywords=kw_list,
        word_count=word_count,
    )
    return f"# {result['title']}\n\n{result['content']}"


# ---------------------------------------------------------------------------
# Humanize sub-agent
# ---------------------------------------------------------------------------


@tool
def humanize(content: str, session_id: str = "") -> str:
    """Remove AI-generated patterns from text so it reads like a human wrote
    it. Fixes em dashes, robotic transitions, hedging language, etc.
    Always run this after generating or revising blog content.

    Args:
        content: The blog content to humanize. Can be empty if session_id is provided.
        session_id: Current session ID to read the draft from store.
    """
    content = _get_draft_content(session_id, content)
    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else ""
    result = run_humanize(content=content, title=title)
    return result["content"]


# ---------------------------------------------------------------------------
# Revise sub-agent
# ---------------------------------------------------------------------------


@tool
def revise(feedback: str, session_id: str = "", current_content: str = "") -> str:
    """Revise blog content based on user feedback. Returns the complete
    revised post in Markdown.

    Args:
        feedback: What the user wants changed.
        session_id: Current session ID — if provided, reads the draft from store.
        current_content: The FULL current blog post. Omit if using session_id.
    """
    current_content = _get_draft_content(session_id, current_content)
    if not current_content:
        return "Error: No draft content available to revise."
    title_match = re.search(r"^#\s+(.+)$", current_content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else ""

    system = (
        "You are an expert blog editor. Revise the post based on the feedback.\n"
        "Keep structure unless asked to change. Preserve Markdown formatting.\n"
        "Return the FULL revised post starting with an H1 heading."
    )
    human = (
        f"Current title: {title}\n\n"
        f"Current post:\n{current_content}\n\n"
        f"Feedback: {feedback}\n\n"
        "Write the revised blog post:"
    )
    chunks: list[str] = []
    emitted = 0
    for chunk in llm.stream([SystemMessage(content=system), HumanMessage(content=human)]):
        text = getattr(chunk, "content", "") or ""
        if not text:
            continue
        chunks.append(text)
        emitted += len(text)
        if emitted >= 240:
            snippet = "".join(chunks)
            get_progress().emit(snippet[-140:].replace("\n", " ").strip())
            emitted = 0
    return "".join(chunks)


# ---------------------------------------------------------------------------
# Publish sub-agents
# ---------------------------------------------------------------------------


@tool
def request_publish_approval(session_id: str = "", title: str = "", content: str = "", keywords: str = "", meta_description: str = "") -> str:
    """Request user approval before publishing a blog post to WordPress.

    This tool MUST be called before publish_to_wordpress. It returns a
    summary of what will be published so the user can confirm or reject.

    Args:
        session_id: Current session ID — reads draft from store if title/content omitted.
        title: The blog post title. Omit to use draft title.
        content: The full Markdown content. Omit to use draft content.
        keywords: Comma-separated focus keywords from SEO analysis.
        meta_description: SEO meta description.
    """
    if session_id and (not title or not content):
        draft = store_module.get_draft(session_id)
        if draft:
            title = title or draft.get("blog_title", "Untitled")
            content = content or draft.get("humanized_content", "")
            keywords = keywords or draft.get("keywords", "")
            meta_description = meta_description or draft.get("meta_description", "")
    word_count = len(content.split()) if content else 0
    excerpt = content[:200].replace("\n", " ").replace("#", "").strip() if content else ""
    summary = (
        f"Ready to publish to WordPress:\n\n"
        f"- **Title:** {title}\n"
        f"- **Words:** {word_count}\n"
        f"- **Focus Keywords:** {keywords}\n"
        f"- **Meta Description:** {meta_description}\n"
        f"- **Preview:** {excerpt}...\n\n"
        f"Waiting for user confirmation."
    )
    return json.dumps({
        "summary": summary,
        "title": title,
        "keywords": keywords,
        "meta_description": meta_description,
    })


@tool
def publish_to_wordpress(session_id: str = "", title: str = "", content: str = "",
                         excerpt: str = "", keywords: str = "", meta_description: str = "") -> str:
    """Publish a blog post to WordPress as a draft with SEO meta tags.

    IMPORTANT: Only call this AFTER the user has explicitly confirmed
    they want to publish. Never call this without user approval.

    Args:
        session_id: Current session ID — reads draft from store if title/content omitted.
        title: Blog post title. Omit to use draft title.
        content: Full Markdown content. Omit to use draft content.
        excerpt: Optional short description.
        keywords: Comma-separated focus keywords for Rank Math SEO.
        meta_description: SEO meta description for Rank Math.
    """
    if session_id and (not title or not content):
        draft = store_module.get_draft(session_id)
        if draft:
            title = title or draft.get("blog_title", "Untitled")
            content = content or draft.get("humanized_content", "")
            keywords = keywords or draft.get("keywords", "")
            meta_description = meta_description or draft.get("meta_description", "")
    meta = {}
    if title:
        meta["rank_math_title"] = title
    if meta_description:
        meta["rank_math_description"] = meta_description
    if keywords:
        meta["rank_math_focus_keyword"] = keywords

    result = run_publisher(
        title=title, content=content, excerpt=excerpt or meta_description,
        status="draft", meta=meta if meta else None,
    )
    if result["success"]:
        return f"Published as draft! Post ID: {result['post_id']}. URL: {result.get('permalink', '')}"
    return f"Publishing failed: {result.get('error', 'Unknown error')}"
# ---------------------------------------------------------------------------


@tool
def convert_to_vlog(session_id: str = "", blog_content: str = "", duration_minutes: int = 10) -> str:
    """Convert a blog post into a video script with timestamps, visual cues,
    and narrator delivery notes.

    Args:
        session_id: Current session ID — reads draft from store if blog_content omitted.
        blog_content: The blog post content. Omit to use current draft.
        duration_minutes: Target duration in minutes.
    """
    blog_content = _get_draft_content(session_id, blog_content)
    result = run_vlog_editor(
        blog_content=blog_content, duration_minutes=duration_minutes
    )
    return result["video_script"]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ALL_TOOLS = [
    web_search,
    research_topic,
    analyze_seo,
    write_blog,
    humanize,
    revise,
    request_publish_approval,
    publish_to_wordpress,
    convert_to_vlog,
]

TOOL_DISPLAY = {
    "web_search": ("Searching", "🔍"),
    "research_topic": ("Researching", "🔬"),
    "analyze_seo": ("SEO Analysis", "⭐"),
    "write_blog": ("Writing Blog", "✍️"),
    "humanize": ("Humanizing", "✨"),
    "revise": ("Revising", "✏️"),
    "request_publish_approval": ("Preparing Preview", "📋"),
    "publish_to_wordpress": ("Publishing", "📤"),
    "convert_to_vlog": ("Video Script", "🎬"),
}
