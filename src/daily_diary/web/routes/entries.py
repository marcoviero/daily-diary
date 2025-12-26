"""Routes for diary entries."""

import tempfile
from datetime import date, datetime, time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ...clients import OuraClient, StravaClient, WeatherClient
from ...models.entry import DiaryEntry
from ...models.health import (
    BodyLocation,
    Incident,
    IncidentType,
    Meal,
    MealType,
    Severity,
    Symptom,
    SymptomType,
)
from ...services.storage import DiaryStorage

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


def get_storage() -> DiaryStorage:
    """Get storage instance."""
    return DiaryStorage()


@router.get("/", response_class=HTMLResponse)
async def list_entries(
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
):
    """List recent diary entries."""
    with get_storage() as storage:
        entries = storage.get_recent_entries(days)
    
    return templates.TemplateResponse(
        "entries/list.html",
        {
            "request": request,
            "entries": entries,
            "days": days,
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def new_entry_form(
    request: Request,
    entry_date: Optional[str] = Query(default=None),
):
    """Show form for new/editing diary entry."""
    target_date = (
        datetime.strptime(entry_date, "%Y-%m-%d").date()
        if entry_date
        else date.today()
    )
    
    with get_storage() as storage:
        entry = storage.get_or_create_entry(target_date)
    
    # Fetch integrations if not already present
    if not entry.integrations.weather:
        weather_client = WeatherClient()
        if weather_client.is_configured:
            entry.integrations.weather = weather_client.get_weather_for_date(target_date)
    
    if not entry.integrations.activities:
        strava_client = StravaClient()
        if strava_client.is_configured:
            entry.integrations.activities = strava_client.get_activities_for_date(target_date)
    
    if not entry.integrations.sleep:
        oura_client = OuraClient()
        if oura_client.is_configured:
            entry.integrations.sleep = oura_client.get_sleep_for_date(target_date)
    
    # Save updated integrations
    with get_storage() as storage:
        storage.save_entry(entry)
    
    return templates.TemplateResponse(
        "entries/form.html",
        {
            "request": request,
            "entry": entry,
            "symptom_types": list(SymptomType),
            "body_locations": list(BodyLocation),
            "incident_types": list(IncidentType),
            "meal_types": list(MealType),
            "severities": list(range(11)),
        },
    )


@router.post("/save")
async def save_entry(
    request: Request,
    entry_date: str = Form(...),
    overall_wellbeing: Optional[int] = Form(default=None),
    energy_level: Optional[int] = Form(default=None),
    stress_level: Optional[int] = Form(default=None),
    mood: Optional[str] = Form(default=None),
    general_notes: Optional[str] = Form(default=None),
):
    """Save the main entry fields."""
    target_date = datetime.strptime(entry_date, "%Y-%m-%d").date()
    
    with get_storage() as storage:
        entry = storage.get_or_create_entry(target_date)
        
        entry.overall_wellbeing = overall_wellbeing
        entry.energy_level = energy_level
        entry.stress_level = stress_level
        entry.mood = mood or None
        entry.general_notes = general_notes or None
        entry.updated_at = datetime.now()
        
        storage.save_entry(entry)
    
    return RedirectResponse(
        url=f"/entries/new?entry_date={entry_date}",
        status_code=303,
    )


@router.post("/symptom")
async def add_symptom(
    request: Request,
    entry_date: str = Form(...),
    symptom_type: str = Form(...),
    custom_type: Optional[str] = Form(default=None),
    severity: int = Form(...),
    location: Optional[str] = Form(default=None),
    custom_location: Optional[str] = Form(default=None),
    onset_time: Optional[str] = Form(default=None),
    notes: Optional[str] = Form(default=None),
):
    """Add a symptom to an entry."""
    target_date = datetime.strptime(entry_date, "%Y-%m-%d").date()
    
    # Parse onset time if provided
    parsed_onset = None
    if onset_time:
        try:
            parsed_onset = datetime.strptime(onset_time, "%H:%M").time()
        except ValueError:
            pass
    
    symptom = Symptom(
        type=SymptomType(symptom_type),
        custom_type=custom_type or None,
        severity=Severity(severity),
        location=BodyLocation(location) if location else None,
        custom_location=custom_location or None,
        onset_time=parsed_onset,
        notes=notes or None,
    )
    
    with get_storage() as storage:
        entry = storage.get_or_create_entry(target_date)
        entry.add_symptom(symptom)
        storage.save_entry(entry)
    
    return RedirectResponse(
        url=f"/entries/new?entry_date={entry_date}",
        status_code=303,
    )


@router.post("/incident")
async def add_incident(
    request: Request,
    entry_date: str = Form(...),
    incident_type: str = Form(...),
    custom_type: Optional[str] = Form(default=None),
    location: str = Form(...),
    custom_location: Optional[str] = Form(default=None),
    severity: int = Form(...),
    description: str = Form(...),
    time_occurred: Optional[str] = Form(default=None),
):
    """Add an incident to an entry."""
    target_date = datetime.strptime(entry_date, "%Y-%m-%d").date()
    
    parsed_time = None
    if time_occurred:
        try:
            parsed_time = datetime.strptime(time_occurred, "%H:%M").time()
        except ValueError:
            pass
    
    incident = Incident(
        type=IncidentType(incident_type),
        custom_type=custom_type or None,
        location=BodyLocation(location),
        custom_location=custom_location or None,
        severity=Severity(severity),
        description=description,
        time_occurred=parsed_time,
    )
    
    with get_storage() as storage:
        entry = storage.get_or_create_entry(target_date)
        entry.add_incident(incident)
        storage.save_entry(entry)
    
    return RedirectResponse(
        url=f"/entries/new?entry_date={entry_date}",
        status_code=303,
    )


@router.post("/meal")
async def add_meal(
    request: Request,
    entry_date: str = Form(...),
    meal_type: str = Form(...),
    description: str = Form(...),
    time_consumed: Optional[str] = Form(default=None),
    contains_alcohol: bool = Form(default=False),
    alcohol_units: Optional[float] = Form(default=None),
    contains_caffeine: bool = Form(default=False),
    notes: Optional[str] = Form(default=None),
):
    """Add a meal to an entry."""
    target_date = datetime.strptime(entry_date, "%Y-%m-%d").date()
    
    parsed_time = None
    if time_consumed:
        try:
            parsed_time = datetime.strptime(time_consumed, "%H:%M").time()
        except ValueError:
            pass
    
    meal = Meal(
        meal_type=MealType(meal_type),
        description=description,
        time_consumed=parsed_time,
        contains_alcohol=contains_alcohol,
        alcohol_units=alcohol_units if contains_alcohol else None,
        contains_caffeine=contains_caffeine,
        notes=notes or None,
    )
    
    with get_storage() as storage:
        entry = storage.get_or_create_entry(target_date)
        entry.add_meal(meal)
        storage.save_entry(entry)
    
    return RedirectResponse(
        url=f"/entries/new?entry_date={entry_date}",
        status_code=303,
    )


@router.post("/complete")
async def mark_complete(
    request: Request,
    entry_date: str = Form(...),
):
    """Mark an entry as complete."""
    target_date = datetime.strptime(entry_date, "%Y-%m-%d").date()
    
    with get_storage() as storage:
        entry = storage.get_or_create_entry(target_date)
        entry.mark_complete()
        storage.save_entry(entry)
    
    return RedirectResponse(url="/entries/", status_code=303)


@router.get("/{entry_date}", response_class=HTMLResponse)
async def view_entry(
    request: Request,
    entry_date: str,
):
    """View a specific entry."""
    target_date = datetime.strptime(entry_date, "%Y-%m-%d").date()
    
    with get_storage() as storage:
        entry = storage.get_entry(target_date)
    
    if entry is None:
        return RedirectResponse(url="/entries/", status_code=303)
    
    return templates.TemplateResponse(
        "entries/view.html",
        {
            "request": request,
            "entry": entry,
        },
    )


# API Endpoints

@router.post("/api/transcribe")
async def transcribe_audio(
    audio: UploadFile = File(...),
    entry_date: str = Form(...),
):
    """
    Transcribe audio recording and append to entry notes.
    
    Uses local faster-whisper (if installed) or OpenAI Whisper API.
    """
    from ...services.transcription import TranscriptionService
    
    target_date = datetime.strptime(entry_date, "%Y-%m-%d").date()
    
    # Check if any transcription method is available
    transcription_service = TranscriptionService()
    
    if not transcription_service.is_configured:
        return JSONResponse(
            {
                "success": False, 
                "error": "No transcription method available.\n\n"
                         "Option 1 (free, local): pip install faster-whisper\n"
                         "Option 2 (API): Add OPENAI_API_KEY to .env"
            },
            status_code=400
        )
    
    tmp_path = None
    try:
        # Save uploaded audio to temp file
        content = await audio.read()
        
        if len(content) < 100:
            return JSONResponse(
                {"success": False, "error": f"Audio file too small ({len(content)} bytes). Recording may have failed."},
                status_code=400
            )
        
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        
        # Transcribe (tries local first, then OpenAI)
        text = transcription_service.transcribe_file(tmp_path)
        
        # Determine which method was used
        method = "local (faster-whisper)" if transcription_service.has_local else "OpenAI API"
        
        if not text:
            return JSONResponse(
                {"success": False, "error": "Transcription returned empty result. Try speaking louder or longer."},
                status_code=400
            )
        
        # Append to entry notes
        with get_storage() as storage:
            entry = storage.get_or_create_entry(target_date)
            
            # Add transcribed text to general notes
            timestamp = datetime.now().strftime("%H:%M")
            new_note = f"[Voice note {timestamp}] {text}"
            
            if entry.general_notes:
                entry.general_notes = f"{entry.general_notes}\n\n{new_note}"
            else:
                entry.general_notes = new_note
            
            entry.updated_at = datetime.now()
            storage.save_entry(entry)
        
        return JSONResponse({
            "success": True,
            "transcription": text,
            "method": method,
            "message": f"Transcription added to notes (via {method})"
        })
        
    except ValueError as e:
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=400
        )
    except RuntimeError as e:
        # OpenAI API errors
        error_msg = str(e)
        if "insufficient_quota" in error_msg.lower() or "429" in error_msg:
            return JSONResponse(
                {"success": False, "error": "OpenAI API quota exceeded. Check your billing at platform.openai.com"},
                status_code=402
            )
        return JSONResponse(
            {"success": False, "error": f"Transcription failed: {error_msg}"},
            status_code=500
        )
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": f"Unexpected error: {type(e).__name__}: {str(e)}"},
            status_code=500
        )
    finally:
        # Clean up temp file
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
