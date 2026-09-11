"""
HTML Page routes serving Jinja2 templates for Dashboard and Document View.
"""

from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# Calculate templates directory relative to project root (5 levels up from pages.py)
PROJECT_ROOT = Path(__file__).resolve().parents[4]
TEMPLATES_DIR = PROJECT_ROOT / "frontend" / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["pages"])


@router.get("/", response_class=HTMLResponse)
async def render_dashboard(request: Request):
    """Render main dashboard page."""
    return templates.TemplateResponse(request=request, name="dashboard.html")


@router.get("/documents/{document_name:path}/view", response_class=HTMLResponse)
async def render_document_result(request: Request, document_name: str):
    """Render detail view page for a specific processed document."""
    return templates.TemplateResponse(
        request=request,
        name="document_result.html",
        context={"document_name": document_name}
    )
