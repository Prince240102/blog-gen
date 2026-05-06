"""
Vlog Content Editor Agent
--------------------------
Converts a written blog post into a video script with timestamps,
visual cues, and narrator notes.
"""

from __future__ import annotations

import re

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from app.services.llm import llm
from app.services.progress import get_progress


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def convert_node(state: dict) -> dict:
    blog_content = state.get("blog_content", "")
    duration = state.get("duration_minutes", 10)
    target_words = duration * 150

    get_progress().emit(f"Creating {duration}-min video script…")

    system = (
        "You are a professional video scriptwriter. Convert blog content into "
        "an engaging vlog script.\n\n"
        "Rules:\n"
        "- Write in a conversational, natural speaking style\n"
        f"- Target duration: {duration} minutes (~{target_words} words)\n"
        "- Include timestamps in [MM:SS] format for each section\n"
        "- Add visual cues in (parentheses) describing B-roll, graphics, etc.\n"
        "- Add narrator delivery notes in **bold** where emphasis is needed\n"
        "- Include a hook/opening and a clear CTA closing"
    )

    human = (
        f"Blog content:\n{blog_content[:6000]}\n\n"
        "Convert this into a vlog video script."
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
    script = "".join(chunks)

    timestamps = _parse_timestamps(script)
    notes = _parse_narrator_notes(script)

    return {
        **state,
        "video_script": script,
        "timestamps": timestamps,
        "narrator_notes": notes,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_timestamps(text: str) -> list[dict]:
    """Extract [MM:SS] timestamps with descriptions."""
    results = []
    for line in text.split("\n"):
        match = re.search(r"\[(\d{1,2}:\d{2})\]\s*(.+)", line)
        if match:
            results.append({
                "time": match.group(1),
                "description": match.group(2).strip(),
            })
    return results[:15]


def _parse_narrator_notes(text: str) -> list[str]:
    """Extract narrator delivery notes (text in **bold**)."""
    notes = re.findall(r"\*\*(.+?)\*\*", text)
    return notes[:20]


# ---------------------------------------------------------------------------
# Build graph
# ---------------------------------------------------------------------------

def _build_graph():
    g = StateGraph(dict)
    g.add_node("convert", convert_node)
    g.set_entry_point("convert")
    g.add_edge("convert", END)
    return g.compile()


vlog_graph = _build_graph()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_vlog_editor(blog_content: str, duration_minutes: int = 10) -> dict:
    result = vlog_graph.invoke({
        "blog_content": blog_content,
        "duration_minutes": duration_minutes,
        "video_script": "",
        "timestamps": [],
        "narrator_notes": [],
    })
    return {
        "video_script": result.get("video_script", ""),
        "timestamps": result.get("timestamps", []),
        "narrator_notes": result.get("narrator_notes", []),
        "estimated_duration_minutes": duration_minutes,
    }
