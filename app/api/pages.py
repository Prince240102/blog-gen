"""
Page Routes
-----------
Serve Jinja2 HTML templates for the frontend UI.
Bypasses Starlette's Jinja2Templates wrapper to avoid
a conflict with LangGraph's StateGraph(dict).
"""

from __future__ import annotations

import os

import jinja2
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

# Direct Jinja2 environment — no Starlette wrapper
_template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(_template_dir),
    autoescape=jinja2.select_autoescape(["html", "xml"]),
)


def _render(template_name: str, **context) -> HTMLResponse:
    tmpl = _jinja_env.get_template(template_name)
    return HTMLResponse(tmpl.render(**context))


@router.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    return _render("pages/login.html", request=request)


@router.get("/app", response_class=HTMLResponse)
async def app_page(request: Request):
    return _render("pages/app.html", request=request)
