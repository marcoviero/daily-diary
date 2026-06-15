"""Routes for data analysis."""

from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from ...services.analysis import AnalysisService
from ...services.database import AnalyticsDB

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")

_EPOCH = date(2020, 1, 1)


def _resolve_date_range(days: int) -> tuple[date, date]:
    """Convert a days parameter to (start_date, end_date).

    Special values:
      days=0  → all time (from earliest record in the DB, or fallback epoch)
      days=-1 → year to date (Jan 1 of current year to today)
    """
    end_date = date.today()
    if days == 0:
        with AnalyticsDB() as db:
            row = db.conn.execute(
                "SELECT MIN(entry_date) FROM daily_summary"
            ).fetchone()
        earliest = row[0] if row and row[0] else _EPOCH.isoformat()
        start_date = date.fromisoformat(earliest)
    elif days == -1:
        start_date = date(end_date.year, 1, 1)
    else:
        start_date = end_date - timedelta(days=days)
    return start_date, end_date


@router.get("/", response_class=HTMLResponse)
async def analysis_dashboard(
    request: Request,
    days: int = Query(default=90, ge=-1),
):
    """Main analysis dashboard."""
    start_date, end_date = _resolve_date_range(days)
    
    service = AnalysisService()
    
    # Get all analysis data
    summary = service.get_summary_stats(start_date, end_date)
    correlations = service.analyze_symptom_correlations(
        target='has_neuralgiaform',  # headache+ = neuralgiform headaches
        start_date=start_date,
        end_date=end_date,
    )
    patterns = service.find_symptom_patterns(start_date, end_date)
    chart_data = service.generate_chart_data(start_date, end_date)
    medication_analysis = service.analyze_medication_effectiveness(start_date, end_date)
    
    # New: Lag correlations and actionable insights
    lag_correlations = service.analyze_lag_correlations(
        target='has_neuralgiaform',  # headache+ = neuralgiform headaches
        start_date=start_date,
        end_date=end_date,
        max_lag_days=3,
    )
    actionable_insights = service.get_actionable_insights(start_date, end_date)
    
    # Fitness metrics (CTL/ATL/TSB)
    fitness_metrics = service.calculate_fitness_metrics(end_date, lookback_days=days)
    
    # Filter to significant correlations for display
    significant_correlations = [c for c in correlations if c.is_significant]
    
    return templates.TemplateResponse(
        "analysis/dashboard.html",
        {
            "request": request,
            "days": days,
            "summary": summary,
            "correlations": correlations[:10],  # Top 10
            "significant_correlations": significant_correlations,
            "patterns": patterns,
            "chart_data": chart_data,
            "medication_analysis": medication_analysis,
            "lag_correlations": lag_correlations,
            "actionable_insights": actionable_insights,
            "fitness_metrics": fitness_metrics,
        },
    )


@router.get("/correlations", response_class=HTMLResponse)
async def correlations_detail(
    request: Request,
    target: str = Query(default="worst_symptom_severity"),
    days: int = Query(default=90, ge=-1),
):
    """Detailed correlation analysis."""
    start_date, end_date = _resolve_date_range(days)
    
    service = AnalysisService()
    correlations = service.analyze_symptom_correlations(
        target=target,
        start_date=start_date,
        end_date=end_date,
    )
    
    return templates.TemplateResponse(
        "analysis/correlations.html",
        {
            "request": request,
            "target": target,
            "days": days,
            "correlations": correlations,
        },
    )


@router.get("/api/chart-data")
async def get_chart_data(
    days: int = Query(default=90, ge=-1),
):
    """API endpoint for chart data (for dynamic updates)."""
    start_date, end_date = _resolve_date_range(days)
    
    service = AnalysisService()
    chart_data = service.generate_chart_data(start_date, end_date)
    
    return JSONResponse(content=chart_data)


@router.get("/api/summary")
async def get_summary(
    days: int = Query(default=90, ge=-1),
):
    """API endpoint for summary statistics."""
    start_date, end_date = _resolve_date_range(days)
    
    service = AnalysisService()
    summary = service.get_summary_stats(start_date, end_date)
    
    return JSONResponse(content=summary)
