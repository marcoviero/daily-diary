"""Routes for user profile management."""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ...services.database import AnalyticsDB

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


@router.get("/", response_class=HTMLResponse)
async def profile_page(request: Request):
    """Show user profile page."""
    with AnalyticsDB() as db:
        profile = db.get_user_profile() or {}
    
    return templates.TemplateResponse(
        "profile/view.html",
        {
            "request": request,
            "profile": profile,
        },
    )


@router.post("/save")
async def save_profile(
    request: Request,
    name: Optional[str] = Form(None),
    date_of_birth: Optional[str] = Form(None),
    height_cm: Optional[float] = Form(None),
    weight_kg: Optional[float] = Form(None),
    blood_type: Optional[str] = Form(None),
    biological_sex: Optional[str] = Form(None),
    conditions: Optional[str] = Form(None),  # Comma-separated
    allergies: Optional[str] = Form(None),  # Comma-separated
    current_medications: Optional[str] = Form(None),  # Comma-separated
    emergency_contact_name: Optional[str] = Form(None),
    emergency_contact_phone: Optional[str] = Form(None),
    emergency_contact_relation: Optional[str] = Form(None),
    primary_care_physician: Optional[str] = Form(None),
    pharmacy: Optional[str] = Form(None),
    health_notes: Optional[str] = Form(None),
):
    """Save user profile."""
    # Parse comma-separated lists
    def parse_list(value: Optional[str]) -> list:
        if not value:
            return []
        return [item.strip() for item in value.split(',') if item.strip()]
    
    profile = {
        'name': name,
        'date_of_birth': date_of_birth if date_of_birth else None,
        'height_cm': height_cm,
        'weight_kg': weight_kg,
        'blood_type': blood_type if blood_type else None,
        'biological_sex': biological_sex if biological_sex else None,
        'conditions': parse_list(conditions),
        'allergies': parse_list(allergies),
        'current_medications': parse_list(current_medications),
        'emergency_contact_name': emergency_contact_name,
        'emergency_contact_phone': emergency_contact_phone,
        'emergency_contact_relation': emergency_contact_relation,
        'primary_care_physician': primary_care_physician,
        'pharmacy': pharmacy,
        'health_notes': health_notes,
    }
    
    with AnalyticsDB() as db:
        db.save_user_profile(profile)
    
    return RedirectResponse(url="/profile/", status_code=303)
