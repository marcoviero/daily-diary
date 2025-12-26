"""Routes for AI Health Advisor (Doctor's Appointment)."""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from ...services.advisor import HealthAdvisor
from ...services.database import AnalyticsDB

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")

# Store advisor sessions (in production, use proper session management)
_advisor_sessions: dict[str, HealthAdvisor] = {}


def get_advisor(session_id: str) -> HealthAdvisor:
    """Get or create an advisor session."""
    if session_id not in _advisor_sessions:
        _advisor_sessions[session_id] = HealthAdvisor()
    return _advisor_sessions[session_id]


@router.get("/", response_class=HTMLResponse)
async def advisor_page(request: Request):
    """Show the doctor's appointment chat interface."""
    advisor = HealthAdvisor()
    
    # Get past consultations
    past_consultations = []
    try:
        with AnalyticsDB() as db:
            df = db.get_consultations(limit=10)
            if not df.empty:
                past_consultations = df.to_dict('records')
    except Exception:
        pass
    
    return templates.TemplateResponse(
        "advisor/chat.html",
        {
            "request": request,
            "is_configured": advisor.is_configured,
            "has_claude": advisor.has_claude,
            "has_openai": advisor.has_openai,
            "past_consultations": past_consultations,
        },
    )


@router.post("/start")
async def start_consultation(
    session_id: str = Form(...),
    days: int = Form(default=30),
):
    """Start a new consultation session."""
    advisor = get_advisor(session_id)
    
    if not advisor.is_configured:
        return JSONResponse({
            "success": False,
            "error": "No AI provider configured. Add ANTHROPIC_API_KEY or OPENAI_API_KEY to .env"
        }, status_code=400)
    
    try:
        greeting, provider = advisor.start_consultation(days, session_id)
        
        return JSONResponse({
            "success": True,
            "message": greeting,
            "provider": provider,
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)


@router.post("/message")
async def send_message(
    session_id: str = Form(...),
    message: str = Form(...),
):
    """Send a message to the health advisor."""
    advisor = get_advisor(session_id)
    
    if not advisor.is_configured:
        return JSONResponse({
            "success": False,
            "error": "No AI provider configured"
        }, status_code=400)
    
    try:
        response, provider = advisor.send_message(message)
        
        return JSONResponse({
            "success": True,
            "message": response,
            "provider": provider,
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)


@router.post("/end")
async def end_consultation(
    session_id: str = Form(...),
):
    """End a consultation session and generate summary."""
    if session_id not in _advisor_sessions:
        return JSONResponse({"success": True, "summary": None})
    
    advisor = _advisor_sessions[session_id]
    
    try:
        result = advisor.end_consultation()
        del _advisor_sessions[session_id]
        
        return JSONResponse({
            "success": True,
            "summary": result.get('summary') if result else None,
        })
    except Exception as e:
        # Clean up session even on error
        if session_id in _advisor_sessions:
            del _advisor_sessions[session_id]
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)


@router.get("/history", response_class=HTMLResponse)
async def consultation_history(request: Request):
    """View past consultation history."""
    consultations = []
    try:
        with AnalyticsDB() as db:
            df = db.get_consultations(limit=50)
            if not df.empty:
                consultations = df.to_dict('records')
    except Exception as e:
        print(f"Error loading consultations: {e}")
    
    return templates.TemplateResponse(
        "advisor/history.html",
        {
            "request": request,
            "consultations": consultations,
        },
    )


@router.get("/consultation/{consultation_id}", response_class=HTMLResponse)
async def view_consultation(request: Request, consultation_id: str):
    """View a specific consultation."""
    consultation = None
    try:
        with AnalyticsDB() as db:
            df = db.query(
                "SELECT * FROM consultations WHERE id = ?",
                [consultation_id]
            )
            if not df.empty:
                consultation = df.to_dict('records')[0]
    except Exception as e:
        print(f"Error loading consultation: {e}")
    
    return templates.TemplateResponse(
        "advisor/view.html",
        {
            "request": request,
            "consultation": consultation,
        },
    )
