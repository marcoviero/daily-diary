"""Command-line interface for Daily Diary."""

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .models.entry import DiaryEntry
from .services import DiaryPrompter, DiaryStorage, TranscriptionService

app = typer.Typer(
    name="diary",
    help="Daily Health Diary - Track symptoms, incidents, and wellness",
    no_args_is_help=True,
)
console = Console()


def parse_date(date_str: Optional[str]) -> date:
    """Parse a date string or return today.
    
    Supports:
    - None or empty: today
    - "today": today
    - "yesterday": yesterday
    - "-N": N days ago (e.g., "-1" = yesterday, "-7" = a week ago)
    - "YYYY-MM-DD": specific date
    """
    if date_str is None or date_str.lower() == "today":
        return date.today()
    
    if date_str.lower() == "yesterday":
        return date.today() - timedelta(days=1)
    
    # Relative days: -1, -2, -7, etc.
    if date_str.startswith("-") and date_str[1:].isdigit():
        days_ago = int(date_str[1:])
        return date.today() - timedelta(days=days_ago)
    
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        console.print(f"[red]Invalid date format: {date_str}[/red]")
        console.print("[dim]Use: YYYY-MM-DD, 'yesterday', or -N (days ago)[/dim]")
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


@app.command()
def sync_db():
    """Sync all diary entries to the analytics database."""
    from .services.database import AnalyticsDB
    
    console.print("Syncing entries to analytics database...")
    
    with DiaryStorage(sync_analytics=False) as storage:
        entries = storage.db.all()
        
        with AnalyticsDB() as analytics:
            for entry_dict in entries:
                entry = DiaryEntry.model_validate(entry_dict)
                analytics.upsert_entry(entry)
                console.print(f"  ✓ {entry.entry_date}")
    
    console.print(f"\n[green]✓ Synced {len(entries)} entries to analytics.duckdb[/green]")


@app.command()
def query(
    sql: str = typer.Argument(..., help="SQL query to run against analytics database"),
):
    """Run a SQL query against the analytics database."""
    from .services.database import AnalyticsDB
    
    with AnalyticsDB() as analytics:
        try:
            df = analytics.query(sql)
            console.print(df.to_string())
        except Exception as e:
            console.print(f"[red]Query error: {e}[/red]")


@app.command()
def correlations(
    days: int = typer.Option(90, "--days", "-n", help="Number of days to analyze"),
):
    """Show correlation analysis from analytics database."""
    import pandas as pd
    from .services.database import AnalyticsDB
    from datetime import timedelta
    
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    
    with AnalyticsDB() as analytics:
        df = analytics.get_daily_summary_df(start_date, end_date)
        
        if df.empty:
            console.print("[yellow]No data in analytics database. Run 'diary sync-db' first.[/yellow]")
            return
        
        console.print(f"\n[bold]Data from {start_date} to {end_date} ({len(df)} days)[/bold]\n")
        
        # Key correlations with symptoms
        if 'worst_symptom_severity' in df.columns:
            target = 'worst_symptom_severity'
            correlations = []
            
            factors = [
                ('pressure_hpa', 'Pressure'),
                ('sleep_score', 'Sleep Score'),
                ('hrv_average', 'HRV'),
                ('total_sleep_minutes', 'Sleep Duration'),
                ('total_activity_minutes', 'Activity'),
                ('alcohol_units', 'Alcohol'),
                ('temp_avg_c', 'Temperature'),
            ]
            
            for col, name in factors:
                if col in df.columns and df[col].notna().sum() >= 5:
                    corr = df[target].corr(df[col])
                    if not pd.isna(corr):
                        correlations.append((name, corr))
            
            correlations.sort(key=lambda x: abs(x[1]), reverse=True)
            
            table = Table(title=f"Correlations with Symptom Severity (last {days} days)")
            table.add_column("Factor", style="cyan")
            table.add_column("Correlation", justify="right")
            table.add_column("Interpretation", style="dim")
            
            for name, corr in correlations:
                color = "green" if corr < 0 else "red"
                interp = "protective" if corr < 0 else "risk factor"
                strength = "weak" if abs(corr) < 0.3 else "moderate" if abs(corr) < 0.5 else "strong"
                table.add_row(
                    name,
                    f"[{color}]{corr:+.3f}[/{color}]",
                    f"{strength} {interp}",
                )
            
            console.print(table)
        else:
            console.print("[yellow]No symptom data found for correlation analysis.[/yellow]")


@app.command()
def schema():
    """Show the database schema."""
    from .services.database import AnalyticsDB
    
    with AnalyticsDB() as analytics:
        console.print(analytics.get_schema_summary())


@app.command()
def tables():
    """List all database tables with row counts."""
    from .services.database import AnalyticsDB
    
    with AnalyticsDB() as analytics:
        table = Table(title="Database Tables")
        table.add_column("Table", style="cyan")
        table.add_column("Rows", justify="right")
        
        table_names = [
            "daily_summary", "sleep", "activities", "meals", "symptoms",
            "incidents", "weather", "vitals", "medications", "supplements", "hydration"
        ]
        
        for tbl in table_names:
            try:
                count = analytics.query(f"SELECT COUNT(*) as n FROM {tbl}")["n"][0]
                table.add_row(tbl, str(count))
            except Exception:
                table.add_row(tbl, "-")
        
        console.print(table)


@app.command()
def log_meal(
    description: str = typer.Argument(..., help="What you ate (e.g., 'burger and fries with a coke')"),
    meal_type: str = typer.Option("snack", "--type", "-t", help="Meal type: breakfast, lunch, dinner, snack"),
    date_str: Optional[str] = typer.Option(None, "--date", "-d", help="Date (YYYY-MM-DD), defaults to today"),
    no_estimate: bool = typer.Option(False, "--no-estimate", help="Skip LLM nutrition estimation"),
):
    """Log a meal with automatic nutrition estimation."""
    from .services.nutrition import NutritionEstimator
    from .services.database import AnalyticsDB
    
    entry_date = parse_date(date_str)
    
    console.print(f"\n[bold]Logging meal for {entry_date}[/bold]")
    console.print(f"  {meal_type.capitalize()}: {description}")
    
    nutrition = {}
    if not no_estimate:
        console.print("\n[dim]Estimating nutrition...[/dim]")
        estimator = NutritionEstimator()
        nutrition = estimator.estimate(description, meal_type)
        
        if nutrition.get("source") == "llm":
            console.print(f"[green]✓ LLM estimation (confidence: {nutrition.get('confidence', 0):.0%})[/green]")
        else:
            console.print("[yellow]⚠ Heuristic estimation (LLM unavailable)[/yellow]")
        
        # Show nutrition summary
        table = Table(title="Nutritional Estimate")
        table.add_column("Nutrient", style="cyan")
        table.add_column("Amount", justify="right")
        
        table.add_row("Calories", f"{nutrition.get('calories', 0):.0f} kcal")
        table.add_row("Protein", f"{nutrition.get('protein_g', 0):.1f} g")
        table.add_row("Carbs", f"{nutrition.get('carbs_g', 0):.1f} g")
        table.add_row("Fat", f"{nutrition.get('fat_g', 0):.1f} g")
        table.add_row("Fiber", f"{nutrition.get('fiber_g', 0):.1f} g")
        
        if nutrition.get('caffeine_mg', 0) > 0:
            table.add_row("Caffeine", f"{nutrition.get('caffeine_mg', 0):.0f} mg")
        if nutrition.get('alcohol_units', 0) > 0:
            table.add_row("Alcohol", f"{nutrition.get('alcohol_units', 0):.1f} units")
        
        console.print(table)
        
        if nutrition.get("reasoning"):
            console.print(f"\n[dim]Reasoning: {nutrition['reasoning']}[/dim]")
    
    # Save to database
    with AnalyticsDB() as analytics:
        meal_id = analytics.add_meal_with_nutrition(
            entry_date=entry_date,
            meal_type=meal_type,
            description=description,
            nutrition=nutrition,
        )
        console.print(f"\n[green]✓ Meal saved (ID: {meal_id[:8]}...)[/green]")


@app.command()
def nutrition(
    days: int = typer.Option(7, "--days", "-n", help="Number of days to show"),
):
    """Show nutrition summary for recent days."""
    from .services.database import AnalyticsDB
    from datetime import timedelta
    
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    
    with AnalyticsDB() as analytics:
        df = analytics.get_nutrition_summary(start_date, end_date)
        
        if df.empty:
            console.print("[yellow]No meal data found. Log meals with 'diary log-meal'[/yellow]")
            return
        
        table = Table(title=f"Nutrition Summary (last {days} days)")
        table.add_column("Date", style="cyan")
        table.add_column("Meals", justify="right")
        table.add_column("Calories", justify="right")
        table.add_column("Protein", justify="right")
        table.add_column("Carbs", justify="right")
        table.add_column("Fat", justify="right")
        
        for _, row in df.iterrows():
            table.add_row(
                str(row['entry_date']),
                str(int(row['meal_count'])),
                f"{row['total_calories']:.0f}" if row['total_calories'] else "-",
                f"{row['total_protein_g']:.0f}g" if row['total_protein_g'] else "-",
                f"{row['total_carbs_g']:.0f}g" if row['total_carbs_g'] else "-",
                f"{row['total_fat_g']:.0f}g" if row['total_fat_g'] else "-",
            )
        
        console.print(table)


@app.command()
def sleep_trends(
    days: int = typer.Option(14, "--days", "-n", help="Number of days to show"),
):
    """Show sleep trends for recent days."""
    from .services.database import AnalyticsDB
    from datetime import timedelta
    
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    
    with AnalyticsDB() as analytics:
        df = analytics.get_sleep_trends(start_date, end_date)
        
        if df.empty:
            console.print("[yellow]No sleep data found. Fetch data with 'diary fetch'[/yellow]")
            return
        
        table = Table(title=f"Sleep Trends (last {days} days)")
        table.add_column("Date", style="cyan")
        table.add_column("Score", justify="right")
        table.add_column("Duration", justify="right")
        table.add_column("Deep", justify="right")
        table.add_column("REM", justify="right")
        table.add_column("HRV", justify="right")
        table.add_column("Efficiency", justify="right")
        
        for _, row in df.iterrows():
            hours = int(row['total_sleep_minutes'] // 60) if row['total_sleep_minutes'] else 0
            mins = int(row['total_sleep_minutes'] % 60) if row['total_sleep_minutes'] else 0
            
            table.add_row(
                str(row['entry_date']),
                f"{int(row['sleep_score'])}" if row['sleep_score'] else "-",
                f"{hours}h {mins}m" if row['total_sleep_minutes'] else "-",
                f"{int(row['deep_sleep_minutes'])}m" if row['deep_sleep_minutes'] else "-",
                f"{int(row['rem_sleep_minutes'])}m" if row['rem_sleep_minutes'] else "-",
                f"{int(row['hrv_average'])}" if row['hrv_average'] else "-",
                f"{int(row['efficiency_percent'])}%" if row['efficiency_percent'] else "-",
            )
        
        console.print(table)


@app.command()
def db_stats():
    """Show database statistics and table sizes."""
    from .services.database import AnalyticsDB
    import os
    
    with AnalyticsDB() as analytics:
        db_path = analytics.db_path
        
        # File size
        file_size = os.path.getsize(db_path) if db_path.exists() else 0
        console.print(f"\n[bold]Database:[/bold] {db_path}")
        console.print(f"[bold]File size:[/bold] {file_size / 1024 / 1024:.2f} MB")
        
        # Check WAL file size
        wal_path = Path(str(db_path) + ".wal")
        if wal_path.exists():
            wal_size = os.path.getsize(wal_path)
            console.print(f"[bold]WAL file:[/bold] {wal_size / 1024 / 1024:.2f} MB")
        
        # Table row counts
        console.print("\n[bold]Table Statistics:[/bold]")
        table = Table()
        table.add_column("Table", style="cyan")
        table.add_column("Rows", justify="right")
        table.add_column("Est. Size", justify="right")
        
        tables = [
            "sleep", "activities", "meals", "symptoms", "incidents",
            "weather", "vitals", "medications", "supplements", 
            "hydration", "daily_summary", "consultations"
        ]
        
        total_rows = 0
        for tbl in tables:
            try:
                result = analytics.conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()
                count = result[0] if result else 0
                total_rows += count
                
                # Estimate size (rough approximation)
                if count > 0:
                    # Get average row size by sampling
                    try:
                        size_result = analytics.conn.execute(f"""
                            SELECT AVG(LENGTH(CAST(* AS VARCHAR))) FROM {tbl} LIMIT 100
                        """).fetchone()
                        avg_size = size_result[0] if size_result and size_result[0] else 100
                        est_size = count * avg_size / 1024  # KB
                        size_str = f"{est_size:.1f} KB" if est_size < 1024 else f"{est_size/1024:.2f} MB"
                    except Exception:
                        size_str = "-"
                else:
                    size_str = "0"
                
                table.add_row(tbl, str(count), size_str)
            except Exception:
                table.add_row(tbl, "-", "-")
        
        console.print(table)
        console.print(f"\n[dim]Total rows: {total_rows}[/dim]")
        
        # Check consultations specifically (likely culprit)
        try:
            conv_result = analytics.conn.execute("""
                SELECT COUNT(*), SUM(LENGTH(conversation_json)) / 1024.0 / 1024.0 as mb
                FROM consultations 
                WHERE conversation_json IS NOT NULL
            """).fetchone()
            if conv_result and conv_result[0] > 0:
                console.print(f"\n[yellow]Conversation transcripts: {conv_result[0]} consultations, {conv_result[1]:.2f} MB[/yellow]")
        except Exception:
            pass
        
        if wal_path.exists() and wal_size > 1024 * 1024:  # > 1MB
            console.print(f"\n[yellow]💡 Run 'diary db-compact' to reclaim WAL space[/yellow]")


@app.command()
def db_compact():
    """Compact database and reclaim disk space."""
    from .services.database import AnalyticsDB
    import os
    
    with AnalyticsDB() as analytics:
        db_path = analytics.db_path
        
        # Size before
        size_before = os.path.getsize(db_path) if db_path.exists() else 0
        wal_path = Path(str(db_path) + ".wal")
        wal_before = os.path.getsize(wal_path) if wal_path.exists() else 0
        
        console.print(f"[dim]Before: {(size_before + wal_before) / 1024 / 1024:.2f} MB[/dim]")
        
        # Checkpoint and vacuum
        console.print("Running CHECKPOINT...")
        analytics.conn.execute("CHECKPOINT")
        
        console.print("Running VACUUM...")
        analytics.conn.execute("VACUUM")
        
        # Size after
        size_after = os.path.getsize(db_path) if db_path.exists() else 0
        wal_after = os.path.getsize(wal_path) if wal_path.exists() else 0
        
        saved = (size_before + wal_before) - (size_after + wal_after)
        console.print(f"[dim]After: {(size_after + wal_after) / 1024 / 1024:.2f} MB[/dim]")
        
        if saved > 0:
            console.print(f"[green]✓ Reclaimed {saved / 1024 / 1024:.2f} MB[/green]")
        else:
            console.print("[yellow]Database already compact[/yellow]")


if __name__ == "__main__":
    app()
