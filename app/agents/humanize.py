"""
Humanize Agent
--------------
Removes AI-generated patterns ("slop") from blog content:
- Em dashes (—) → regular dashes or remove
- Quotation marks with spaces → standard quotes
- Excessive hedging language
- Robot-like transitions
- Overuse of certain phrases
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from app.services.llm import llm
from app.services.progress import get_progress


def humanize_node(state: dict) -> dict:
    """Transform AI-generated content to sound human-written."""
    content = state.get("content", "")
    title = state.get("title", "")

    get_progress().emit("Removing AI patterns…")

    system = (
        "You are an expert editor. Transform AI-generated blog content to sound "
        "naturally written by a human.\n\n"
        "Remove or fix:\n"
        "- Em dashes (—) — replace with standard dashes or remove entirely\n"
        "- Excessive em dashes in sequence\n"
        "- Hedging language like 'It is important to note', 'One could argue'\n"
        "- Robotic transitions like 'Furthermore', 'Additionally', 'In conclusion'\n"
        "- Overuse of words like 'essentially', 'actually', 'literally'\n"
        "- Square brackets with [citation needed] style placeholders\n"
        "- Text within asterisks that's not actual emphasis\n"
        "- Formal/stiff phrasing that sounds unnatural\n\n"
        "Keep the content accurate and well-structured. "
        "Write in a conversational but professional tone.\n"
        "Preserve all headings (##) and formatting.\n"
        "Return ONLY the revised content, no explanations."
    )

    human = f"Title: {title}\n\nContent:\n{content}"

    # Stream edits into step_progress so the UI shows motion.
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
    humanized = "".join(chunks).strip()

    return {
        **state,
        "humanized_content": humanized or content,
    }


def _build_graph() -> StateGraph:
    g = StateGraph(dict)
    g.add_node("humanize", humanize_node)
    g.set_entry_point("humanize")
    g.add_edge("humanize", END)
    return g.compile()


humanize_graph = _build_graph()


def run_humanize(content: str, title: str = "") -> dict:
    """Humanize blog content."""
    result = humanize_graph.invoke(
        {
            "content": content,
            "title": title,
        }
    )
    return {
        "content": result.get("humanized_content", content),
    }
