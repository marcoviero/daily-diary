"""Routes for data analysis."""

from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from ...services.analysis import AnalysisService

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


@router.get("/", response_class=HTMLResponse)
async def analysis_dashboard(
    request: Request,
    days: int = Query(default=90, ge=7, le=365),
):
    """Main analysis dashboard."""
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    
    service = AnalysisService()
    
    # Get all analysis data
    summary = service.get_summary_stats(start_date, end_date)
    correlations = service.analyze_symptom_correlations(
        target='worst_symptom_severity',
        start_date=start_date,
        end_date=end_date,
    )
    patterns = service.find_symptom_patterns(start_date, end_date)
    chart_data = service.generate_chart_data(start_date, end_date)
    medication_analysis = service.analyze_medication_effectiveness(start_date, end_date)
    
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
        },
    )


@router.get("/correlations", response_class=HTMLResponse)
async def correlations_detail(
    request: Request,
    target: str = Query(default="worst_symptom_severity"),
    days: int = Query(default=90, ge=7, le=365),
):
    """Detailed correlation analysis."""
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    
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
    days: int = Query(default=90, ge=7, le=365),
):
    """API endpoint for chart data (for dynamic updates)."""
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    
    service = AnalysisService()
    chart_data = service.generate_chart_data(start_date, end_date)
    
    return JSONResponse(content=chart_data)


@router.get("/api/summary")
async def get_summary(
    days: int = Query(default=90, ge=7, le=365),
):
    """API endpoint for summary statistics."""
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    
    service = AnalysisService()
    summary = service.get_summary_stats(start_date, end_date)
    
    return JSONResponse(content=summary)
