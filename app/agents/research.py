"""
Research Agent
--------------
Searches the web via Brave Search API and/or Serper (Google Search API),
then analyses the results with the LLM to extract insights useful for
blog writing.
"""

from __future__ import annotations

import datetime
import json

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from app.core.config import settings
from app.services.llm import llm_fast
from app.services.progress import get_progress


# ---------------------------------------------------------------------------
# Unified search — tries multiple providers
# ---------------------------------------------------------------------------

def _brave_search(query: str) -> list[dict]:
    """Call Brave Search API. Returns list of result dicts or empty list."""
    api_key = settings.brave_api_key
    if not api_key:
        return []

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

        results = []
        for item in data.get("web", {}).get("results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "description": item.get("description", ""),
                "source": "brave",
            })
        return results
    except Exception:
        return []


def _serper_search(query: str) -> list[dict]:
    """Call Serper (Google Search API). Returns list of result dicts."""
    api_key = settings.serper_api_key
    if not api_key:
        return []

    try:
        resp = httpx.post(
            "https://google.serper.dev/search",
            json={"q": query, "num": 10},
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        # Serper returns organic results
        for item in data.get("organic", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "description": item.get("snippet", ""),
                "source": "serper",
            })
        return results
    except Exception:
        return []


def _merge_results(brave_results: list[dict], serper_results: list[dict]) -> list[dict]:
    """Merge results from both providers, deduplicating by URL."""
    seen = set()
    merged = []

    # Interleave: 2 from Brave, 2 from Serper, etc.
    max_len = max(len(brave_results), len(serper_results))
    for i in range(max_len):
        for source in (brave_results, serper_results):
            if i < len(source):
                url = source[i].get("url", "")
                if url and url not in seen:
                    seen.add(url)
                    merged.append(source[i])

    return merged


def search_web(query: str) -> list[dict]:
    """Search using all configured providers and return merged results."""
    brave = _brave_search(query)
    serper = _serper_search(query)

    if not brave and not serper:
        return []

    return _merge_results(brave, serper)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def search_node(state: dict) -> dict:
    """Call configured search APIs."""
    query = state.get("query", "")
    if not query:
        return {**state, "raw_results": "No query provided."}

    # Inject current date for time-sensitive queries
    today = datetime.datetime.now()
    date_context = today.strftime("%B %Y")
    enriched_query = f"{query} {date_context}"

    get_progress().emit(f"Searching for \"{enriched_query[:60]}…\"")

    results = search_web(enriched_query)

    if not results:
        get_progress().emit("No results found, trying general knowledge…")
        return {
            **state,
            "raw_results": (
                f"No search results found for '{enriched_query}'. "
                "No search APIs are configured or all requests failed."
            ),
        }

    get_progress().emit(f"Found {len(results)} results, analyzing…")
    raw = json.dumps(results, indent=2)
    return {**state, "raw_results": raw}


def analyze_node(state: dict) -> dict:
    """Use the LLM to distil the search results into actionable insights."""
    query = state.get("query", "")
    raw = state.get("raw_results", "")
    today = datetime.datetime.now().strftime("%B %Y")

    # If search failed or no API key, be honest
    if not raw or "not configured" in raw or "No search results" in raw:
        return {
            **state,
            "analysis": (
                f"**Research Status**: No live search data available ({raw or 'empty results'}).\n\n"
                f"**Recommendation**: The agent cannot verify current facts for '{query}'. "
                "Please provide specific details or proceed with general knowledge."
            ),
        }

    get_progress().emit("Analyzing search results…")

    system = (
        "You are a research analyst. You MUST base your brief ONLY on the web "
        "search results provided below. Do NOT invent facts, models, dates, or "
        "statistics that are not explicitly in the search results.\n\n"
        "If the search results are sparse, outdated, or irrelevant, say so.\n\n"
        f"Today's date is {today}."
    )

    human = (
        f"Topic: {query}\n\n"
        f"Web search results (ONLY use these):\n{raw}\n\n"
        "Produce a structured research brief. Be concise.\n"
        "1. **Key findings** – facts/stats from the results ONLY\n"
        "2. **Trending angles** – perspectives supported by the results\n"
        "3. **Suggested outline** – 4-6 section headings\n"
        "4. **Sources** – authoritative URLs from the results"
    )

    response = llm_fast.invoke([SystemMessage(content=system), HumanMessage(content=human)])

    get_progress().emit("Research complete")
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
