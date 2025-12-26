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
    Medication,
    MedicationForm,
    Severity,
    Supplement,
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
    from ...services.routines import RoutinesService
    from ...services.database import AnalyticsDB
    from ...models.health import Meal, MealType
    from datetime import timedelta
    
    target_date = (
        datetime.strptime(entry_date, "%Y-%m-%d").date()
        if entry_date
        else date.today()
    )
    
    with get_storage() as storage:
        entry = storage.get_or_create_entry(target_date)
        # Get previous day's entry for defaults
        previous_date = target_date - timedelta(days=1)
        previous_entry = storage.get_entry(previous_date)
    
    # Load meals from DuckDB (source of truth for meals)
    meals_with_ids = []
    with AnalyticsDB() as analytics:
        import pandas as pd
        
        meals_df = analytics.conn.execute("""
            SELECT id, meal_type, description, time_consumed, 
                   calories, protein_g, carbs_g, fat_g,
                   contains_caffeine, contains_alcohol, alcohol_units
            FROM meals
            WHERE entry_date = ?
            ORDER BY time_consumed ASC NULLS LAST, created_at ASC
        """, [target_date]).df()
        
        if not meals_df.empty:
            entry.meals = []
            for _, row in meals_df.iterrows():
                meal = Meal(
                    meal_type=MealType(row['meal_type']) if pd.notna(row['meal_type']) else MealType.SNACK,
                    description=row['description'] if pd.notna(row['description']) else "",
                    time_consumed=row['time_consumed'] if pd.notna(row['time_consumed']) else None,
                    calories=row['calories'] if pd.notna(row['calories']) else None,
                    protein_g=row['protein_g'] if pd.notna(row['protein_g']) else None,
                    carbs_g=row['carbs_g'] if pd.notna(row['carbs_g']) else None,
                    fat_g=row['fat_g'] if pd.notna(row['fat_g']) else None,
                    contains_caffeine=bool(row['contains_caffeine']) if pd.notna(row['contains_caffeine']) else False,
                    contains_alcohol=bool(row['contains_alcohol']) if pd.notna(row['contains_alcohol']) else False,
                    alcohol_units=row['alcohol_units'] if pd.notna(row['alcohol_units']) else None,
                )
                entry.meals.append(meal)
                meals_with_ids.append({
                    'id': row['id'],
                    'meal': meal,
                })
    
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
    
    # Get routines and calculate totals
    routines_service = RoutinesService()
    routine_categories = routines_service.get_categories()
    
    # Initialize quick_log with defaults if empty
    if not entry.quick_log:
        entry.quick_log = routines_service.get_default_counts()
    
    quick_log_totals = routines_service.calculate_totals(entry.quick_log)
    
    # Build previous day defaults for assessment
    prev_defaults = {
        "overall_wellbeing": previous_entry.overall_wellbeing if previous_entry else None,
        "energy_level": previous_entry.energy_level if previous_entry else None,
        "stress_level": previous_entry.stress_level if previous_entry else None,
        "mood": previous_entry.mood if previous_entry else None,
    }
    
    # Save updated integrations and quick_log (but NOT meals - they live in DuckDB)
    with get_storage() as storage:
        storage.save_entry(entry)
    
    return templates.TemplateResponse(
        "entries/form.html",
        {
            "request": request,
            "entry": entry,
            "meals_with_ids": meals_with_ids,
            "symptom_types": list(SymptomType),
            "body_locations": list(BodyLocation),
            "incident_types": list(IncidentType),
            "meal_types": list(MealType),
            "severities": list(range(11)),
            "routine_categories": routine_categories,
            "quick_log_totals": quick_log_totals,
            "prev_defaults": prev_defaults,
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
    from ...services.database import AnalyticsDB
    from ...services.nutrition import NutritionEstimator
    
    target_date = datetime.strptime(entry_date, "%Y-%m-%d").date()
    
    parsed_time = None
    if time_consumed:
        try:
            parsed_time = datetime.strptime(time_consumed, "%H:%M").time()
        except ValueError:
            pass
    
    # Estimate nutrition
    estimator = NutritionEstimator()
    nutrition = estimator.estimate(description, meal_type)
    
    # Add caffeine/alcohol info to nutrition dict
    if contains_caffeine and not nutrition.get('caffeine_mg'):
        nutrition['caffeine_mg'] = 100  # Default estimate
    if contains_alcohol:
        nutrition['alcohol_units'] = alcohol_units or 1.0
    
    # Save to DuckDB (single source of truth for meals)
    with AnalyticsDB() as analytics:
        analytics.add_meal_with_nutrition(
            entry_date=target_date,
            meal_type=meal_type,
            description=description,
            nutrition=nutrition,
            time_consumed=parsed_time,
            notes=notes,
        )
    
    return RedirectResponse(
        url=f"/entries/new?entry_date={entry_date}",
        status_code=303,
    )


@router.post("/meal/delete")
async def delete_meal(
    request: Request,
    meal_id: str = Form(...),
    entry_date: str = Form(...),
):
    """Delete a meal."""
    from ...services.database import AnalyticsDB
    
    with AnalyticsDB() as analytics:
        analytics.conn.execute("DELETE FROM meals WHERE id = ?", [meal_id])
        analytics.conn.execute("CHECKPOINT")
    
    return RedirectResponse(
        url=f"/entries/new?entry_date={entry_date}",
        status_code=303,
    )


@router.post("/medication")
async def add_medication(
    request: Request,
    entry_date: str = Form(...),
    name: str = Form(...),
    dosage: Optional[str] = Form(default=None),
    form: Optional[str] = Form(default=None),
    time_taken: Optional[str] = Form(default=None),
    reason: Optional[str] = Form(default=None),
):
    """Add a medication to an entry."""
    target_date = datetime.strptime(entry_date, "%Y-%m-%d").date()
    
    parsed_time = None
    if time_taken:
        try:
            parsed_time = datetime.strptime(time_taken, "%H:%M").time()
        except ValueError:
            pass
    
    med_form = None
    if form:
        try:
            med_form = MedicationForm(form)
        except ValueError:
            med_form = MedicationForm.OTHER
    
    medication = Medication(
        name=name,
        dosage=dosage or None,
        form=med_form,
        time_taken=parsed_time,
        reason=reason or None,
    )
    
    with get_storage() as storage:
        entry = storage.get_or_create_entry(target_date)
        entry.add_medication(medication)
        storage.save_entry(entry)
    
    return RedirectResponse(
        url=f"/entries/new?entry_date={entry_date}",
        status_code=303,
    )


@router.post("/supplement")
async def add_supplement(
    request: Request,
    entry_date: str = Form(...),
    name: str = Form(...),
    dosage: Optional[str] = Form(default=None),
    time_taken: Optional[str] = Form(default=None),
):
    """Add a supplement to an entry."""
    target_date = datetime.strptime(entry_date, "%Y-%m-%d").date()
    
    parsed_time = None
    if time_taken:
        try:
            parsed_time = datetime.strptime(time_taken, "%H:%M").time()
        except ValueError:
            pass
    
    supplement = Supplement(
        name=name,
        dosage=dosage or None,
        time_taken=parsed_time,
    )
    
    with get_storage() as storage:
        entry = storage.get_or_create_entry(target_date)
        entry.add_supplement(supplement)
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
    parse_content: bool = Form(default=True),  # Whether to parse and extract structured data
):
    """
    Transcribe audio recording, parse it, and populate diary entry.
    
    Uses local faster-whisper (if installed) or OpenAI Whisper API for transcription.
    Uses Claude or OpenAI to parse the content and extract structured data.
    """
    from ...services.transcription import TranscriptionService
    from ...services.diary_parser import DiaryParser
    
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
        transcription_method = "local (faster-whisper)" if transcription_service.has_local else "OpenAI API"
        
        if not text:
            return JSONResponse(
                {"success": False, "error": "Transcription returned empty result. Try speaking louder or longer."},
                status_code=400
            )
        
        # Parse the transcribed text and extract structured data
        parsed_data = None
        parse_summary = None
        
        if parse_content:
            parser = DiaryParser()
            if parser.is_configured:
                parsed_data = parser.parse(text)
        
        # Apply to entry
        with get_storage() as storage:
            entry = storage.get_or_create_entry(target_date)
            
            # Add transcribed text to general notes (always keep the raw transcription)
            timestamp = datetime.now().strftime("%H:%M")
            new_note = f"[Voice note {timestamp}] {text}"
            
            if entry.general_notes:
                entry.general_notes = f"{entry.general_notes}\n\n{new_note}"
            else:
                entry.general_notes = new_note
            
            # If we parsed successfully, apply the extracted data
            if parsed_data and parsed_data.get("success"):
                parser = DiaryParser()
                parse_summary = parser.apply_to_entry(parsed_data, entry)
            
            entry.updated_at = datetime.now()
            storage.save_entry(entry)
        
        # Build response
        response_data = {
            "success": True,
            "transcription": text,
            "transcription_method": transcription_method,
        }
        
        if parsed_data and parsed_data.get("success"):
            response_data["parsing"] = {
                "success": True,
                "provider": parsed_data.get("provider"),
                "extracted": parse_summary,
            }
            
            # Build a human-readable summary
            parts = []
            if parse_summary.get("meals_added"):
                parts.append(f"{parse_summary['meals_added']} meal(s)")
            if parse_summary.get("medications_added"):
                parts.append(f"{parse_summary['medications_added']} medication(s)")
            if parse_summary.get("supplements_added"):
                parts.append(f"{parse_summary['supplements_added']} supplement(s)")
            if parse_summary.get("symptoms_added"):
                parts.append(f"{parse_summary['symptoms_added']} symptom(s)")
            if parse_summary.get("incidents_added"):
                parts.append(f"{parse_summary['incidents_added']} incident(s)")
            if parse_summary.get("wellbeing_updated"):
                parts.append("wellbeing scores")
            
            if parts:
                response_data["message"] = f"Transcribed and extracted: {', '.join(parts)}"
            else:
                response_data["message"] = "Transcribed (no structured data extracted)"
        else:
            response_data["parsing"] = {
                "success": False,
                "reason": "Parser not configured or failed" if parse_content else "Parsing disabled",
            }
            response_data["message"] = f"Transcription added to notes (via {transcription_method})"
        
        return JSONResponse(response_data)
        
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


@router.post("/api/quick-log")
async def update_quick_log(
    entry_date: str = Form(...),
    item_id: Optional[str] = Form(default=None),
    count: Optional[float] = Form(default=None),
    action: Optional[str] = Form(default=None),  # 'reset_defaults' or 'clear_all'
):
    """
    Update quick log counts for an entry.
    
    Can update a single item count, reset to defaults, or clear all.
    """
    from ...services.routines import RoutinesService
    
    target_date = datetime.strptime(entry_date, "%Y-%m-%d").date()
    routines_service = RoutinesService()
    
    try:
        with get_storage() as storage:
            entry = storage.get_or_create_entry(target_date)
            
            # Initialize quick_log if empty
            if not entry.quick_log:
                entry.quick_log = {}
            
            if action == "reset_defaults":
                # Reset to default counts
                entry.quick_log = routines_service.get_default_counts()
            elif action == "clear_all":
                # Clear all counts to zero
                entry.quick_log = {k: 0 for k in routines_service.get_default_counts()}
            elif item_id and count is not None:
                # Update single item
                entry.quick_log[item_id] = max(0, count)
            
            entry.updated_at = datetime.now()
            storage.save_entry(entry)
            
            # Calculate updated totals
            totals = routines_service.calculate_totals(entry.quick_log)
        
        return JSONResponse({
            "success": True,
            "quick_log": entry.quick_log,
            "totals": totals,
        })
        
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500
        )
