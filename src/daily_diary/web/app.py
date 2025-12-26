"""FastAPI web application."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .routes import advisor, analysis, entries, meals

# Paths
WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

# Create FastAPI app
app = FastAPI(
    title="Daily Health Diary",
    description="Personal health tracking with automated data integration",
    version="0.1.0",
)

# Mount static files
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Templates
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Include routers
app.include_router(entries.router, prefix="/entries", tags=["entries"])
app.include_router(meals.router, prefix="/meals", tags=["meals"])
app.include_router(analysis.router, prefix="/analysis", tags=["analysis"])
app.include_router(advisor.router, prefix="/advisor", tags=["advisor"])


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page - redirect to today's entry."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/entries/new", status_code=302)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
