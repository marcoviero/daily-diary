"""Routes for meals and nutrition tracking."""

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ...services.database import AnalyticsDB

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


@router.get("/", response_class=HTMLResponse)
async def meals_list(
    request: Request,
    days: int = Query(default=7, ge=1, le=90),
):
    """Show meals and nutrition summary."""
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    
    meals_by_date = {}
    daily_totals = {}
    
    with AnalyticsDB() as analytics:
        import pandas as pd
        
        # Get meals from database
        meals_df = pd.read_sql("""
            SELECT 
                id,
                entry_date,
                meal_type,
                description,
                time_consumed,
                calories,
                protein_g,
                carbs_g,
                fat_g,
                fiber_g,
                caffeine_mg,
                alcohol_units,
                created_at
            FROM meals
            WHERE entry_date >= ? AND entry_date <= ?
            ORDER BY entry_date DESC, time_consumed ASC
        """, analytics.conn, params=[start_date.isoformat(), end_date.isoformat()])
        
        # Group meals by date
        if not meals_df.empty:
            for entry_date in meals_df['entry_date'].unique():
                date_meals = meals_df[meals_df['entry_date'] == entry_date]
                meals_by_date[entry_date] = date_meals.to_dict('records')
                
                # Calculate daily totals
                daily_totals[entry_date] = {
                    'calories': date_meals['calories'].sum() or 0,
                    'protein_g': date_meals['protein_g'].sum() or 0,
                    'carbs_g': date_meals['carbs_g'].sum() or 0,
                    'fat_g': date_meals['fat_g'].sum() or 0,
                    'fiber_g': date_meals['fiber_g'].sum() or 0,
                    'caffeine_mg': date_meals['caffeine_mg'].sum() or 0,
                    'alcohol_units': date_meals['alcohol_units'].sum() or 0,
                    'meal_count': len(date_meals),
                }
        
        # Get weekly averages
        weekly_avg = {}
        if not meals_df.empty:
            weekly_avg = {
                'calories': meals_df.groupby('entry_date')['calories'].sum().mean() or 0,
                'protein_g': meals_df.groupby('entry_date')['protein_g'].sum().mean() or 0,
                'carbs_g': meals_df.groupby('entry_date')['carbs_g'].sum().mean() or 0,
                'fat_g': meals_df.groupby('entry_date')['fat_g'].sum().mean() or 0,
            }
    
    return templates.TemplateResponse(
        "meals/list.html",
        {
            "request": request,
            "meals_by_date": meals_by_date,
            "daily_totals": daily_totals,
            "weekly_avg": weekly_avg,
            "days": days,
            "start_date": start_date,
            "end_date": end_date,
        },
    )


@router.post("/quick-add")
async def quick_add_meal(
    request: Request,
    description: str = Form(...),
    meal_type: str = Form(default="snack"),
    entry_date: Optional[str] = Form(default=None),
):
    """Quick add a meal with nutrition estimation."""
    from ...services.nutrition import NutritionEstimator
    from ...services.database import AnalyticsDB
    
    target_date = (
        datetime.strptime(entry_date, "%Y-%m-%d").date()
        if entry_date
        else date.today()
    )
    
    # Estimate nutrition
    estimator = NutritionEstimator()
    nutrition = estimator.estimate(description, meal_type)
    
    # Save to database
    with AnalyticsDB() as analytics:
        analytics.add_meal_with_nutrition(
            entry_date=target_date,
            meal_type=meal_type,
            description=description,
            nutrition=nutrition,
        )
    
    return RedirectResponse(url="/meals/", status_code=303)


@router.post("/delete")
async def delete_meal(
    request: Request,
    meal_id: str = Form(...),
):
    """Delete a meal."""
    from datetime import datetime
    
    with AnalyticsDB() as analytics:
        # Get entry_date before deleting
        result = analytics.conn.execute(
            "SELECT entry_date FROM meals WHERE id = ?", [meal_id]
        ).fetchone()
        
        if result:
            entry_date_str = result[0]
            analytics.conn.execute("DELETE FROM meals WHERE id = ?", [meal_id])
            analytics.conn.commit()
            # Sync meal totals after deletion
            target_date = datetime.strptime(entry_date_str, "%Y-%m-%d").date()
            analytics.sync_meal_totals(target_date)
    
    return RedirectResponse(url="/meals/", status_code=303)
