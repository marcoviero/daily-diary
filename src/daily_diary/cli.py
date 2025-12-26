"""Command-line interface for Daily Diary."""

from datetime import date, datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .services import DiaryPrompter, DiaryStorage, TranscriptionService

app = typer.Typer(
    name="diary",
    help="Daily Health Diary - Track symptoms, incidents, and wellness",
    no_args_is_help=True,
)
console = Console()


def parse_date(date_str: Optional[str]) -> date:
    """Parse a date string or return today."""
    if date_str is None:
        return date.today()
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        console.print(f"[red]Invalid date format: {date_str}. Use YYYY-MM-DD[/red]")
        raise typer.Exit(1)


@app.command()
def new(
    date_str: Optional[str] = typer.Argument(
        None,
        help="Date for entry (YYYY-MM-DD). Defaults to today.",
    ),
):
    """Start a new diary entry or continue an existing one."""
    entry_date = parse_date(date_str)
    
    prompter = DiaryPrompter()
    prompter.start_entry(entry_date)


@app.command()
def symptom(
    date_str: Optional[str] = typer.Option(
        None, "--date", "-d",
        help="Date for entry (YYYY-MM-DD). Defaults to today.",
    ),
):
    """Quick symptom logging."""
    entry_date = parse_date(date_str)
    
    prompter = DiaryPrompter()
    prompter.quick_symptom(entry_date)


@app.command()
def show(
    date_str: Optional[str] = typer.Argument(
        None,
        help="Date to show (YYYY-MM-DD). Defaults to today.",
    ),
):
    """Show a diary entry."""
    entry_date = parse_date(date_str)
    
    with DiaryStorage() as storage:
        entry = storage.get_entry(entry_date)
        
        if entry is None:
            console.print(f"[yellow]No entry found for {entry_date}[/yellow]")
            raise typer.Exit(0)
        
        # Display entry
        console.print(Panel(
            entry.summary(),
            title=f"📔 {entry_date.strftime('%A, %B %d, %Y')}",
        ))
        
        # Symptoms
        if entry.symptoms:
            console.print("\n[bold]Symptoms:[/bold]")
            for s in entry.symptoms:
                console.print(f"  • {s.display_type}: severity {s.severity.value}/10")
                if s.notes:
                    console.print(f"    [dim]{s.notes}[/dim]")
        
        # Incidents
        if entry.incidents:
            console.print("\n[bold]Incidents:[/bold]")
            for i in entry.incidents:
                console.print(f"  • {i.display_type} ({i.location.value}): {i.description}")
        
        # Notes
        if entry.general_notes:
            console.print(f"\n[bold]Notes:[/bold] {entry.general_notes}")


@app.command(name="list")
def list_entries(
    days: int = typer.Option(
        7, "--days", "-n",
        help="Number of days to show",
    ),
):
    """List recent diary entries."""
    with DiaryStorage() as storage:
        entries = storage.get_recent_entries(days)
        
        if not entries:
            console.print("[yellow]No entries found[/yellow]")
            raise typer.Exit(0)
        
        table = Table(title=f"Recent Entries (last {days} days)")
        table.add_column("Date", style="cyan")
        table.add_column("Wellbeing", justify="center")
        table.add_column("Symptoms", justify="center")
        table.add_column("Activity", justify="right")
        table.add_column("Sleep", justify="center")
        table.add_column("Weather", justify="right")
        table.add_column("✓", justify="center")
        
        for entry in entries:
            # Activity
            activity_mins = entry.integrations.total_activity_minutes
            elevation = entry.integrations.total_elevation_gain
            activity_str = "-"
            if activity_mins:
                activity_str = f"{activity_mins:.0f}m"
                if elevation:
                    activity_str += f" ({elevation:.0f}m↑)"
            
            # Sleep
            sleep_str = "-"
            if entry.integrations.sleep and entry.integrations.sleep.sleep_score:
                sleep_str = str(entry.integrations.sleep.sleep_score)
            
            # Weather
            weather_str = "-"
            if entry.integrations.weather:
                w = entry.integrations.weather
                parts = []
                if w.temp_avg_c:
                    parts.append(f"{w.temp_avg_c:.0f}°C")
                if w.pressure_hpa:
                    parts.append(f"{w.pressure_hpa:.0f}hPa")
                weather_str = " ".join(parts) if parts else "-"
            
            # Symptoms with severity coloring
            symptom_str = "[green]✓[/green]"
            if entry.symptoms:
                worst = entry.worst_symptom_severity
                color = "green" if worst <= 2 else "yellow" if worst <= 5 else "red"
                symptom_str = f"[{color}]{len(entry.symptoms)} ({worst}/10)[/{color}]"
            
            table.add_row(
                entry.entry_date.strftime("%Y-%m-%d"),
                f"{entry.overall_wellbeing or '-'}/10",
                symptom_str,
                activity_str,
                sleep_str,
                weather_str,
                "✓" if entry.is_complete else "",
            )
        
        console.print(table)


@app.command()
def search(
    query: str = typer.Argument(..., help="Search term"),
):
    """Search diary entries."""
    with DiaryStorage() as storage:
        entries = storage.search_entries(query)
        
        if not entries:
            console.print(f"[yellow]No entries found matching '{query}'[/yellow]")
            raise typer.Exit(0)
        
        console.print(f"Found {len(entries)} entries matching '{query}':\n")
        
        for entry in entries[:10]:  # Limit to 10 results
            console.print(Panel(
                entry.summary(),
                title=entry.entry_date.strftime("%Y-%m-%d"),
            ))


@app.command()
def transcribe(
    audio_file: Path = typer.Argument(
        ...,
        help="Path to audio file to transcribe",
        exists=True,
    ),
    date_str: Optional[str] = typer.Option(
        None, "--date", "-d",
        help="Date for entry (YYYY-MM-DD). Defaults to today.",
    ),
):
    """Transcribe an audio file and add to notes."""
    entry_date = parse_date(date_str)
    
    transcription_service = TranscriptionService()
    
    if not transcription_service.is_configured:
        console.print("[red]Transcription not configured. Set OPENAI_API_KEY in .env[/red]")
        raise typer.Exit(1)
    
    console.print(f"Transcribing {audio_file.name}...")
    
    text = transcription_service.transcribe_file(audio_file)
    
    if text is None:
        console.print("[red]Transcription failed[/red]")
        raise typer.Exit(1)
    
    console.print(Panel(text, title="Transcription"))
    
    # Offer to save to entry
    if typer.confirm("Add to today's notes?"):
        with DiaryStorage() as storage:
            entry = storage.get_or_create_entry(entry_date)
            
            if entry.general_notes:
                entry.general_notes += f"\n\n[Voice note]\n{text}"
            else:
                entry.general_notes = f"[Voice note]\n{text}"
            
            storage.save_entry(entry)
            console.print("[green]✓ Added to notes[/green]")


@app.command()
def status():
    """Show configuration and integration status."""
    from .utils.config import get_settings
    
    settings = get_settings()
    
    table = Table(title="Configuration Status")
    table.add_column("Integration", style="cyan")
    table.add_column("Status", justify="center")
    
    integrations = [
        ("Weather (OpenWeatherMap)", settings.has_weather),
        ("Exercise (Strava)", settings.has_strava),
        ("Sleep (Oura Ring)", settings.has_oura),
        ("Transcription (OpenAI)", settings.has_transcription),
    ]
    
    for name, configured in integrations:
        status = "[green]✓ Configured[/green]" if configured else "[yellow]Not configured[/yellow]"
        table.add_row(name, status)
    
    console.print(table)
    console.print(f"\nData directory: {settings.data_dir.absolute()}")
    console.print(f"Location: {settings.default_latitude}, {settings.default_longitude}")


@app.command()
def web(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind to"),
):
    """Start the web interface."""
    import uvicorn
    
    console.print(f"[green]Starting web interface at http://{host}:{port}[/green]")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")
    
    uvicorn.run(
        "daily_diary.web.app:app",
        host=host,
        port=port,
        reload=True,
    )


@app.command()
def fetch(
    date_str: Optional[str] = typer.Argument(
        None,
        help="Date to fetch data for (YYYY-MM-DD). Defaults to today.",
    ),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Force re-fetch even if data exists",
    ),
):
    """Fetch integration data (weather, Strava, Oura) for a date."""
    from .clients import OuraClient, StravaClient, WeatherClient
    
    entry_date = parse_date(date_str)
    
    with DiaryStorage() as storage:
        entry = storage.get_or_create_entry(entry_date)
        
        # Weather
        if force or not entry.integrations.weather:
            weather = WeatherClient()
            if weather.is_configured:
                console.print("Fetching weather...", end=" ")
                data = weather.get_weather_for_date(entry_date)
                if data:
                    entry.integrations.weather = data
                    console.print(f"[green]✓[/green] {data.temp_avg_c:.0f}°C, {data.pressure_hpa} hPa")
                else:
                    console.print("[yellow]no data[/yellow]")
            else:
                console.print("[dim]Weather not configured[/dim]")
        
        # Strava
        if force or not entry.integrations.activities:
            strava = StravaClient()
            if strava.is_configured:
                console.print("Fetching Strava activities...", end=" ")
                activities = strava.get_activities_for_date(entry_date)
                if activities:
                    entry.integrations.activities = activities
                    total_mins = sum(a.duration_minutes for a in activities)
                    console.print(f"[green]✓[/green] {len(activities)} activities ({total_mins:.0f} min)")
                else:
                    console.print("[yellow]no activities[/yellow]")
            else:
                console.print("[dim]Strava not configured[/dim]")
        
        # Oura
        if force or not entry.integrations.sleep:
            oura = OuraClient()
            if oura.is_configured:
                console.print("Fetching Oura sleep...", end=" ")
                sleep = oura.get_sleep_for_date(entry_date)
                if sleep:
                    entry.integrations.sleep = sleep
                    console.print(f"[green]✓[/green] Sleep score: {sleep.sleep_score}")
                else:
                    console.print("[yellow]no data[/yellow]")
            else:
                console.print("[dim]Oura not configured[/dim]")
        
        storage.save_entry(entry)
        console.print(f"\n[green]✓ Entry updated for {entry_date}[/green]")


if __name__ == "__main__":
    app()
