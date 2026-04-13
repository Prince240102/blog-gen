"""
Research Agent
--------------
Searches the web via the Brave Search API, then analyses the results
with the LLM to extract insights useful for blog writing.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from app.core.config import settings
from app.services.llm import llm_fast


# ---------------------------------------------------------------------------
# Graph state
# ---------------------------------------------------------------------------

class ResearchState(Dict):
    """Mutable dict-based state passed between nodes."""
    # inputs
    query: str
    # intermediate
    raw_results: str
    # output
    analysis: str


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def search_node(state: dict) -> dict:
    """Call Brave Web Search API."""
    query = state.get("query", "")
    if not query:
        return {**state, "raw_results": "No query provided."}

    api_key = settings.brave_api_key
    if not api_key:
        return {**state, "raw_results": "Brave API key not configured – skipping web search."}

    try:
        resp = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={
                "q": query,
                "count": 10,
                "text_decorations": False,
            },
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": api_key,
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()

        # Extract the most useful bits
        results: list[dict] = []
        for item in data.get("web", {}).get("results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "description": item.get("description", ""),
            })

        raw = json.dumps(results, indent=2)
        return {**state, "raw_results": raw}

    except Exception as exc:
        return {**state, "raw_results": f"Search error: {exc}"}


def analyze_node(state: dict) -> dict:
    """Use the LLM to distil the search results into actionable insights."""
    query = state.get("query", "")
    raw = state.get("raw_results", "")

    system = (
        "You are a research analyst. Your job is to analyse web search results "
        "and produce a concise brief that a content writer can use to craft a "
        "high-quality blog post."
    )

    human = (
        f"Topic: {query}\n\n"
        f"Search results:\n{raw}\n\n"
        "Produce a structured research brief with:\n"
        "1. **Key findings** – the most important facts/stats\n"
        "2. **Trending angles** – unique perspectives worth covering\n"
        "3. **Suggested outline** – 4-6 section headings\n"
        "4. **Sources** – list any URLs that seem authoritative"
    )

    response = llm_fast.invoke([SystemMessage(content=system), HumanMessage(content=human)])
    return {**state, "analysis": response.content}


# ---------------------------------------------------------------------------
# Build graph
# ---------------------------------------------------------------------------

def _build_graph() -> StateGraph:
    g = StateGraph(dict)
    g.add_node("search", search_node)
    g.add_node("analyze", analyze_node)
    g.set_entry_point("search")
    g.add_edge("search", "analyze")
    g.add_edge("analyze", END)
    return g.compile()


research_graph = _build_graph()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_research(query: str) -> dict:
    """Run the full research pipeline and return structured output."""
    result = research_graph.invoke({"query": query, "raw_results": "", "analysis": ""})
    return {
        "query": query,
        "raw_results": result.get("raw_results", ""),
        "analysis": result.get("analysis", ""),
    }
