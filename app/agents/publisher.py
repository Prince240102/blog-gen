"""
WordPress Publisher Agent
-------------------------
Publishes blog posts directly to a WordPress site via the REST API
using application passwords.
"""

from __future__ import annotations

import base64
import re

import httpx
from langgraph.graph import END, StateGraph

from app.core.config import settings

try:
    from markdown_it import MarkdownIt
except ImportError:
    MarkdownIt = None


def _markdown_to_html(markdown: str) -> str:
    """Convert markdown to HTML, removing H1 heading if present."""
    # Remove H1 heading (# Title) from content to avoid redundancy
    lines = markdown.split("\n")
    if lines and lines[0].strip().startswith("# "):
        lines = lines[1:]
    markdown = "\n".join(lines)

    if MarkdownIt is None:
        return markdown.replace("\n", "<br>\n")

    md = MarkdownIt()
    html = md.render(markdown)
    return html





# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def publish_node(state: dict) -> dict:
    title = state.get("title", "Untitled")
    markdown_content = state.get("content", "")
    excerpt = state.get("excerpt", "")
    status = state.get("status", "draft")
    categories = state.get("categories", [])
    tags = state.get("tags", [])
    slug = state.get("slug")
    author = state.get("author", 1)
    featured_media = state.get("featured_media")
    acf = state.get("acf")
    meta = state.get("meta")

    base_url = settings.wordpress_url
    username = settings.wordpress_username
    app_password = settings.wordpress_app_password

    if not all([base_url, username, app_password]):
        return {
            **state,
            "publish_success": False,
            "publish_error": "WordPress is not configured. Set WORDPRESS_URL, "
            "WORDPRESS_USERNAME, and WORDPRESS_APP_PASSWORD.",
        }

    # Convert markdown to HTML
    content = _markdown_to_html(markdown_content)

    # Generate slug from title if not provided
    if not slug:
        slug = re.sub(r"[^\w\s-]", "", title.lower())
        slug = re.sub(r"[\s-]+", "-", slug).strip("-")

    credentials = base64.b64encode(f"{username}:{app_password}".encode()).decode()
    headers = {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/json",
    }

    payload = {
        "title": title,
        "slug": slug,
        "content": content,
        "excerpt": excerpt[:200] if excerpt else "",
        "status": status,
    }
    if categories:
        payload["categories"] = categories
    if tags:
        payload["tags"] = tags
    if featured_media:
        payload["featured_media"] = featured_media
    if acf:
        payload["acf"] = acf
    if meta:
        payload["meta"] = meta

    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            resp = client.post(
                f"{base_url.rstrip('/')}/wp-json/wp/v2/posts",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            post_status = data.get("status", "draft")
            permalink = data.get("link", "")
            # WordPress runs behind the internal docker hostname (http://wordpress),
            # but users need links that work from their browser.
            public_base = (settings.wordpress_public_url or settings.wordpress_url or "").rstrip("/")
            if public_base:
                permalink = re.sub(r"^http://wordpress(?::\d+)?", public_base, permalink)
            # For drafts, return admin edit URL instead of public permalink
            edit_url = (
                f"{public_base}/wp-admin/post.php?post={data.get('id')}&action=edit"
                if public_base
                else f"/wp-admin/post.php?post={data.get('id')}&action=edit"
            )
            return {
                **state,
                "publish_success": True,
                "publish_post_id": data.get("id"),
                "publish_permalink": edit_url if post_status == "draft" else permalink,
                "publish_status": post_status,
            }
    except httpx.HTTPStatusError as exc:
        return {
            **state,
            "publish_success": False,
            "publish_error": f"HTTP {exc.response.status_code}: {exc.response.text[:500]}",
        }
    except Exception as exc:
        return {
            **state,
            "publish_success": False,
            "publish_error": str(exc),
        }


# ---------------------------------------------------------------------------
# Build graph
# ---------------------------------------------------------------------------


def _build_graph():
    g = StateGraph(dict)
    g.add_node("publish", publish_node)
    g.set_entry_point("publish")
    g.add_edge("publish", END)
    return g.compile()


publish_graph = _build_graph()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_publisher(
    title: str,
    content: str,
    excerpt: str = "",
    status: str = "draft",
    author: int = 1,
    categories: list[int] | None = None,
    tags: list[int] | None = None,
    slug: str | None = None,
    featured_media: int | None = None,
    acf: dict | None = None,
    meta: dict | None = None,
) -> dict:
    result = publish_graph.invoke(
        {
            "title": title,
            "content": content,
            "excerpt": excerpt,
            "status": status,
            "author": author,
            "categories": categories or [],
            "tags": tags or [],
            "slug": slug,
            "featured_media": featured_media,
            "acf": acf,
            "meta": meta,
            "publish_success": False,
            "publish_error": "",
        }
    )

    output = {"success": result.get("publish_success", False)}

    if output["success"]:
        output["post_id"] = result.get("publish_post_id")
        output["permalink"] = result.get("publish_permalink")
        output["status"] = result.get("publish_status")
    else:
        output["error"] = result.get("publish_error", "Unknown error")

    return output
