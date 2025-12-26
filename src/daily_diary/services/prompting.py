"""Interactive prompting service for diary entries."""

from datetime import date, time
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from ..clients import OuraClient, StravaClient, WeatherClient
from ..models.entry import DiaryEntry
from ..models.health import (
    BodyLocation,
    Incident,
    IncidentType,
    Meal,
    MealType,
    Severity,
    Symptom,
    SymptomType,
)
from .storage import DiaryStorage


class DiaryPrompter:
    """
    Interactive prompting system for diary entries.
    
    Guides the user through completing their daily entry with
    smart prompts and auto-fetched data.
    """
    
    def __init__(
        self,
        storage: Optional[DiaryStorage] = None,
        weather_client: Optional[WeatherClient] = None,
        strava_client: Optional[StravaClient] = None,
        oura_client: Optional[OuraClient] = None,
    ):
        self.storage = storage or DiaryStorage()
        self.weather = weather_client or WeatherClient()
        self.strava = strava_client or StravaClient()
        self.oura = oura_client or OuraClient()
        self.console = Console()
    
    def start_entry(self, entry_date: Optional[date] = None) -> DiaryEntry:
        """
        Start or continue a diary entry for the given date.
        
        Guides the user through all sections with smart prompts.
        """
        entry_date = entry_date or date.today()
        entry = self.storage.get_or_create_entry(entry_date)
        
        self.console.print(Panel(
            f"[bold blue]Daily Diary Entry[/bold blue]\n"
            f"Date: {entry_date.strftime('%A, %B %d, %Y')}",
            title="📔 Daily Diary",
        ))
        
        # Fetch automatic data first
        self._fetch_integrations(entry)
        
        # Show what we auto-collected
        self._show_integrations_summary(entry)
        
        # Interactive sections
        self._prompt_wellbeing(entry)
        self._prompt_symptoms(entry)
        self._prompt_incidents(entry)
        self._prompt_meals(entry)
        self._prompt_notes(entry)
        
        # Save and show summary
        entry.mark_complete()
        self.storage.save_entry(entry)
        
        self.console.print("\n")
        self.console.print(Panel(
            entry.summary(),
            title="✅ Entry Saved",
            style="green",
        ))
        
        return entry
    
    def _fetch_integrations(self, entry: DiaryEntry) -> None:
        """Fetch data from integrated services."""
        self.console.print("\n[dim]Fetching data from integrations...[/dim]")
        
        # Weather
        if self.weather.is_configured:
            weather = self.weather.get_weather_for_date(entry.entry_date)
            if weather:
                entry.integrations.weather = weather
                self.console.print("  ✓ Weather data fetched")
        
        # Strava
        if self.strava.is_configured:
            activities = self.strava.get_activities_for_date(entry.entry_date)
            if activities:
                entry.integrations.activities = activities
                self.console.print(f"  ✓ {len(activities)} activities fetched from Strava")
        
        # Oura
        if self.oura.is_configured:
            sleep = self.oura.get_sleep_for_date(entry.entry_date)
            if sleep:
                entry.integrations.sleep = sleep
                self.console.print("  ✓ Sleep data fetched from Oura")
    
    def _show_integrations_summary(self, entry: DiaryEntry) -> None:
        """Display summary of auto-fetched data."""
        if not any([
            entry.integrations.weather,
            entry.integrations.activities,
            entry.integrations.sleep,
        ]):
            return
        
        self.console.print("\n[bold]Auto-collected data:[/bold]")
        
        if entry.integrations.weather:
            w = entry.integrations.weather
            self.console.print(
                f"  🌤️  Weather: {w.description or 'N/A'}, "
                f"{w.temp_avg_f:.0f}°F, "
                f"Pressure: {w.pressure_hpa} hPa"
            )
        
        if entry.integrations.activities:
            for a in entry.integrations.activities:
                self.console.print(
                    f"  🚴 {a.activity_type}: {a.name or 'Untitled'} - "
                    f"{a.duration_minutes:.0f} min, "
                    f"{a.distance_km:.1f} km" if a.distance_km else ""
                )
        
        if entry.integrations.sleep:
            s = entry.integrations.sleep
            self.console.print(
                f"  😴 Sleep: {s.total_sleep_minutes or 0 // 60}h {s.total_sleep_minutes or 0 % 60}m, "
                f"Score: {s.sleep_score or 'N/A'}"
            )
    
    def _prompt_wellbeing(self, entry: DiaryEntry) -> None:
        """Prompt for overall wellbeing metrics."""
        self.console.print("\n[bold cyan]Daily Assessment[/bold cyan]")
        
        entry.overall_wellbeing = IntPrompt.ask(
            "Overall wellbeing (1-10)",
            default=entry.overall_wellbeing or 5,
            choices=[str(i) for i in range(1, 11)],
        )
        
        entry.energy_level = IntPrompt.ask(
            "Energy level (1-10)",
            default=entry.energy_level or 5,
            choices=[str(i) for i in range(1, 11)],
        )
        
        entry.stress_level = IntPrompt.ask(
            "Stress level (1-10)",
            default=entry.stress_level or 5,
            choices=[str(i) for i in range(1, 11)],
        )
    
    def _prompt_symptoms(self, entry: DiaryEntry) -> None:
        """Prompt for symptoms."""
        self.console.print("\n[bold cyan]Symptoms[/bold cyan]")
        
        if entry.symptoms:
            self.console.print(f"[dim]({len(entry.symptoms)} symptom(s) already logged)[/dim]")
        
        while Confirm.ask("Log a symptom?", default=False):
            symptom = self._create_symptom()
            entry.add_symptom(symptom)
            self.console.print(f"  ✓ Added: {symptom.display_type} (severity {symptom.severity.value}/10)")
    
    def _create_symptom(self) -> Symptom:
        """Interactive symptom creation."""
        # Show symptom types
        type_choices = [t.value for t in SymptomType]
        self.console.print("\nSymptom types:", ", ".join(type_choices))
        
        type_str = Prompt.ask(
            "Type",
            choices=type_choices,
            default="headache",
        )
        symptom_type = SymptomType(type_str)
        
        custom_type = None
        if symptom_type == SymptomType.OTHER:
            custom_type = Prompt.ask("Describe the symptom")
        
        severity = IntPrompt.ask(
            "Severity (0-10)",
            default=5,
            choices=[str(i) for i in range(11)],
        )
        
        # Location (optional)
        location = None
        custom_location = None
        if Confirm.ask("Specify body location?", default=False):
            loc_choices = [l.value for l in BodyLocation]
            loc_str = Prompt.ask("Location", choices=loc_choices)
            location = BodyLocation(loc_str)
            if location == BodyLocation.OTHER:
                custom_location = Prompt.ask("Describe location")
        
        notes = Prompt.ask("Notes (optional)", default="") or None
        
        return Symptom(
            type=symptom_type,
            custom_type=custom_type,
            severity=Severity(severity),
            location=location,
            custom_location=custom_location,
            notes=notes,
        )
    
    def _prompt_incidents(self, entry: DiaryEntry) -> None:
        """Prompt for incidents (falls, bumps, etc.)."""
        self.console.print("\n[bold cyan]Incidents[/bold cyan]")
        
        if entry.incidents:
            self.console.print(f"[dim]({len(entry.incidents)} incident(s) already logged)[/dim]")
        
        while Confirm.ask("Log an incident (fall, bump, etc.)?", default=False):
            incident = self._create_incident()
            entry.add_incident(incident)
            self.console.print(f"  ✓ Added: {incident.display_type} - {incident.description[:50]}")
    
    def _create_incident(self) -> Incident:
        """Interactive incident creation."""
        type_choices = [t.value for t in IncidentType]
        type_str = Prompt.ask("Type", choices=type_choices, default="bump")
        incident_type = IncidentType(type_str)
        
        custom_type = None
        if incident_type == IncidentType.OTHER:
            custom_type = Prompt.ask("Describe the incident type")
        
        loc_choices = [l.value for l in BodyLocation]
        loc_str = Prompt.ask("Body location affected", choices=loc_choices)
        location = BodyLocation(loc_str)
        
        custom_location = None
        if location == BodyLocation.OTHER:
            custom_location = Prompt.ask("Describe location")
        
        severity = IntPrompt.ask(
            "Severity of incident (0-10)",
            default=3,
            choices=[str(i) for i in range(11)],
        )
        
        description = Prompt.ask("What happened?")
        
        return Incident(
            type=incident_type,
            custom_type=custom_type,
            location=location,
            custom_location=custom_location,
            severity=Severity(severity),
            description=description,
        )
    
    def _prompt_meals(self, entry: DiaryEntry) -> None:
        """Prompt for meals and food/drink."""
        self.console.print("\n[bold cyan]Meals & Drinks[/bold cyan]")
        
        if entry.meals:
            self.console.print(f"[dim]({len(entry.meals)} meal(s) already logged)[/dim]")
        
        while Confirm.ask("Log a meal or drink?", default=False):
            meal = self._create_meal()
            entry.add_meal(meal)
            self.console.print(f"  ✓ Added: {meal.meal_type.value} - {meal.description[:50]}")
    
    def _create_meal(self) -> Meal:
        """Interactive meal creation."""
        type_choices = [t.value for t in MealType]
        type_str = Prompt.ask("Meal type", choices=type_choices, default="lunch")
        meal_type = MealType(type_str)
        
        description = Prompt.ask("What did you eat/drink?")
        
        contains_alcohol = Confirm.ask("Contains alcohol?", default=False)
        alcohol_units = None
        if contains_alcohol:
            alcohol_units = float(Prompt.ask("How many standard drinks?", default="1"))
        
        contains_caffeine = Confirm.ask("Contains caffeine?", default=False)
        
        return Meal(
            meal_type=meal_type,
            description=description,
            contains_alcohol=contains_alcohol,
            alcohol_units=alcohol_units,
            contains_caffeine=contains_caffeine,
        )
    
    def _prompt_notes(self, entry: DiaryEntry) -> None:
        """Prompt for free-form notes."""
        self.console.print("\n[bold cyan]Notes[/bold cyan]")
        
        if Confirm.ask("Add general notes?", default=False):
            entry.general_notes = Prompt.ask("Notes")
    
    def quick_symptom(
        self,
        entry_date: Optional[date] = None,
    ) -> DiaryEntry:
        """Quick symptom logging without full entry flow."""
        entry_date = entry_date or date.today()
        entry = self.storage.get_or_create_entry(entry_date)
        
        symptom = self._create_symptom()
        entry.add_symptom(symptom)
        self.storage.save_entry(entry)
        
        self.console.print(f"\n✓ Symptom logged for {entry_date}")
        return entry
