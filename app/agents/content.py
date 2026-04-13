"""
Blog Content Generator Agent
-----------------------------
Uses the research brief + SEO keywords to write a full blog post.
"""

from __future__ import annotations

import re

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from app.services.llm import llm


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def generate_node(state: dict) -> dict:
    """Generate the blog post from research data and SEO keywords."""
    topic = state.get("topic", "")
    research = state.get("research", "")
    keywords = state.get("keywords", [])
    style = state.get("style", "informative")
    word_count = state.get("word_count", 1500)

    kw_str = ", ".join(keywords) if keywords else "general"

    system = (
        "You are a world-class blog writer. You write engaging, SEO-friendly, "
        "well-structured blog posts in Markdown format.\n\n"
        "Rules:\n"
        "- Start with a single H1 heading (the title)\n"
        "- Use H2/H3 headings for sections\n"
        "- Include the target keywords naturally throughout\n"
        f"- Aim for approximately {word_count} words\n"
        "- End with a clear call-to-action\n"
        "- Use bullet points or numbered lists where appropriate\n"
        "- Write in an {style} tone"
    )

    human = (
        f"Topic: {topic}\n"
        f"Target keywords: {kw_str}\n\n"
        f"Research brief:\n{research[:5000]}\n\n"
        "Write the full blog post now."
    )

    resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=human)])
    content = resp.content

    # Extract title from first H1 or first non-empty line
    title = _extract_title(content)

    return {
        **state,
        "blog_title": title,
        "blog_content": content,
        "blog_word_count": len(content.split()),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_title(content: str) -> str:
    # Try H1 first
    m = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if m:
        return m.group(1).strip()
    # Fall back to first non-empty line
    for line in content.split("\n"):
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    return "Untitled"


# ---------------------------------------------------------------------------
# Build graph
# ---------------------------------------------------------------------------

def _build_graph():
    g = StateGraph(dict)
    g.add_node("generate", generate_node)
    g.set_entry_point("generate")
    g.add_edge("generate", END)
    return g.compile()


content_graph = _build_graph()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_content_generator(
    topic: str,
    research: str,
    keywords: list[str] | None = None,
    style: str = "informative",
    word_count: int = 1500,
) -> dict:
    result = content_graph.invoke({
        "topic": topic,
        "research": research,
        "keywords": keywords or [],
        "style": style,
        "word_count": word_count,
        "blog_title": "",
        "blog_content": "",
        "blog_word_count": 0,
    })
    return {
        "title": result.get("blog_title", "Untitled"),
        "content": result.get("blog_content", ""),
        "word_count": result.get("blog_word_count", 0),
    }
