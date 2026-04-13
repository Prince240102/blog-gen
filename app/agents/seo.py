"""
SEO Optimiser Agent
-------------------
Optimizes content for search engine ranking by making actual improvements:
- keyword placement and density
- heading structure
- meta description
- readability improvements
- internal linking suggestions
"""

from __future__ import annotations

import re
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from app.services.llm import llm, llm_fast


# ---------------------------------------------------------------------------
# Graph state
# ---------------------------------------------------------------------------

# State is a plain dict so LangGraph can merge updates easily.

# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def extract_keywords_node(state: dict) -> dict:
    """Ask the LLM to extract/expand keywords from the research brief."""
    research = state.get("research", "")
    topic = state.get("topic", "")

    system = (
        "You are an SEO expert. Extract the best target keywords for a blog post."
        "Return ONLY a JSON array of strings, nothing else. Example: "
        '["keyword one", "keyword two"]'
    )
    human = f"Topic: {topic}\n\nResearch brief:\n{research[:4000]}"

    resp = llm_fast.invoke([SystemMessage(content=system), HumanMessage(content=human)])

    # Parse the JSON list from the response
    try:
        # Try to find a JSON array in the response
        match = re.search(r"\[.*\]", resp.content, re.DOTALL)
        if match:
            import json

            keywords = json.loads(match.group())
        else:
            keywords = [k.strip().strip('"- ') for k in resp.content.split("\n") if k.strip()][:10]
    except Exception:
        keywords = [topic]

    return {**state, "keywords": keywords}


def optimize_node(state: dict) -> dict:
    """Optimize content for better SEO ranking."""
    content = state.get("content", state.get("research", ""))
    keywords = state.get("keywords", [])
    kw_str = ", ".join(keywords) if keywords else "general"

    system = (
        "You are an elite SEO consultant. You MUST actually improve the content "
        "to achieve better search engine rankings. Don't just analyze - make changes.\n\n"
        "Apply these improvements:\n"
        "- Place primary keyword in title, first paragraph, and headings\n"
        "- Ensure keyword density of 1-2%\n"
        "- Add H2/H3 subheadings with keyword-rich titles\n"
        "- Include the target keywords in the first 100 words\n"
        "- Add bullet points for key information\n"
        "- Ensure content is scannable and well-structured\n"
        "- Add a compelling meta description (max 160 chars)\n"
        "- Improve readability: shorter paragraphs, active voice\n"
        "- Include a clear introduction and conclusion\n"
        "- Use semantically related terms naturally\n\n"
        "Return your answer in EXACTLY this format:\n\n"
        "META_DESCRIPTION:\n"
        "<max 160 chars, compelling description with primary keyword>\n\n"
        "OPTIMIZED_CONTENT:\n"
        "<the full content, rewritten with ALL SEO improvements applied - "
        "include keywords naturally, better structure, improved readability>"
    )
    human = (
        f"Target keywords: {kw_str}\n\n"
        f"Content to optimize:\n{content[:6000]}\n\n"
        "Rewrite the content with SEO improvements applied. "
        "Make actual changes, not just suggestions."
    )

    resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=human)])
    text = resp.content

    # --- Parse structured sections ---
    meta = _section(text, "META_DESCRIPTION")[:160]
    optimized = _section(text, "OPTIMIZED_CONTENT")

    # Extract keywords found in optimized content for reporting
    found_keywords = [kw for kw in keywords if kw.lower() in optimized.lower()][:5]

    return {
        **state,
        "seo_meta_description": meta,
        "keywords": found_keywords or keywords,
        "optimized_content": optimized or content,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _section(text: str, header: str) -> str:
    """Extract the text after a HEADER: line until the next header or end."""
    pattern = rf"{header}:\s*\n(.*?)(?=\n[A-Z_]+:|\Z)"
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _parse_int(text: str, default: int = 0) -> int:
    m = re.search(r"\d+", text)
    return int(m.group()) if m else default


# ---------------------------------------------------------------------------
# Build graph
# ---------------------------------------------------------------------------


def _build_graph() -> StateGraph:
    g = StateGraph(dict)
    g.add_node("extract_keywords", extract_keywords_node)
    g.add_node("optimize", optimize_node)
    g.set_entry_point("extract_keywords")
    g.add_edge("extract_keywords", "optimize")
    g.add_edge("optimize", END)
    return g.compile()


seo_graph = _build_graph()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_seo(topic: str, research: str, content: str = "") -> dict:
    """Run SEO optimisation pipeline."""
    result = seo_graph.invoke(
        {
            "topic": topic,
            "research": research,
            "content": content,
            "keywords": [],
        }
    )
    return {
        "meta_description": result.get("seo_meta_description", ""),
        "keywords": result.get("keywords", []),
        "seo_score": result.get("seo_score", 0),
        "suggestions": result.get("seo_suggestions", []),
        "optimized_content": result.get("optimized_content", ""),
    }
