"""FastAPI web application."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .routes import advisor, analysis, entries, meals

# Paths
WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

# Create FastAPI app
app = FastAPI(
    title="Daily Health Diary",
    description="Personal health tracking with automated data integration",
    version="0.1.0",
)

# Mount static files
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Templates
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Include routers
app.include_router(entries.router, prefix="/entries", tags=["entries"])
app.include_router(meals.router, prefix="/meals", tags=["meals"])
app.include_router(analysis.router, prefix="/analysis", tags=["analysis"])
app.include_router(advisor.router, prefix="/advisor", tags=["advisor"])


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page - redirect to today's entry."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/entries/new", status_code=302)


@app.get("/help", response_class=HTMLResponse)
async def help_page(request: Request):
    """CLI commands reference page."""
    return templates.TemplateResponse("help.html", {"request": request})


@app.get("/sql/", response_class=HTMLResponse)
async def sql_explorer(request: Request):
    """SQL explorer page."""
    import os
    from ..services.database import AnalyticsDB
    from ..utils.config import get_settings
    
    settings = get_settings()
    db_path = settings.data_dir / "analytics.db"
    wal_path = Path(str(db_path) + "-wal")  # SQLite uses -wal
    
    db_size_mb = os.path.getsize(db_path) / 1024 / 1024 if db_path.exists() else 0
    wal_size_mb = os.path.getsize(wal_path) / 1024 / 1024 if wal_path.exists() else 0
    
    tables = []
    table_sizes = []
    
    try:
        with AnalyticsDB() as db:
            # Get table names and row counts
            tables_df = db.conn.execute("""
                SELECT name 
                FROM sqlite_master 
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
            """).fetchall()
            
            for (table_name,) in tables_df:
                try:
                    count = db.conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
                    tables.append({"name": table_name, "rows": count})
                except:
                    tables.append({"name": table_name, "rows": "?"})
            
            # SQLite doesn't have per-table size info, so just show total
            # We'll skip table_sizes for now
                
    except Exception as e:
        pass
    
    return templates.TemplateResponse("sql.html", {
        "request": request,
        "tables": tables,
        "table_sizes": table_sizes,
        "db_size_mb": db_size_mb,
        "wal_size_mb": wal_size_mb,
        "results": None,
        "columns": [],
        "error": None,
        "last_query": None,
    })


@app.post("/sql/", response_class=HTMLResponse)
async def sql_query(request: Request):
    """Execute SQL query."""
    import os
    import time
    from fastapi import Form
    from ..services.database import AnalyticsDB
    from ..utils.config import get_settings
    
    form_data = await request.form()
    sql = form_data.get("sql", "").strip()
    
    settings = get_settings()
    db_path = settings.data_dir / "analytics.db"
    wal_path = Path(str(db_path) + "-wal")
    
    db_size_mb = os.path.getsize(db_path) / 1024 / 1024 if db_path.exists() else 0
    wal_size_mb = os.path.getsize(wal_path) / 1024 / 1024 if wal_path.exists() else 0
    
    tables = []
    table_sizes = []
    results = None
    columns = []
    error = None
    execution_time = None
    
    try:
        with AnalyticsDB() as db:
            # Get table info
            tables_df = db.conn.execute("""
                SELECT name 
                FROM sqlite_master 
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
            """).fetchall()
            
            for (table_name,) in tables_df:
                try:
                    count = db.conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
                    tables.append({"name": table_name, "rows": count})
                except:
                    tables.append({"name": table_name, "rows": "?"})
            
            # Execute query
            if sql:
                # Security: only allow SELECT and PRAGMA
                sql_upper = sql.upper().strip()
                if not (sql_upper.startswith("SELECT") or 
                        sql_upper.startswith("PRAGMA")):
                    error = "Only SELECT and PRAGMA queries are allowed"
                else:
                    start = time.time()
                    result = db.conn.execute(sql)
                    columns = [desc[0] for desc in result.description] if result.description else []
                    results = result.fetchall()
                    execution_time = time.time() - start
                    
                    # Limit results to prevent browser crash
                    if len(results) > 1000:
                        results = results[:1000]
                        error = f"Results truncated to 1000 rows (query returned more)"
                        
    except Exception as e:
        error = str(e)
    
    return templates.TemplateResponse("sql.html", {
        "request": request,
        "tables": tables,
        "table_sizes": table_sizes,
        "db_size_mb": db_size_mb,
        "wal_size_mb": wal_size_mb,
        "results": results,
        "columns": columns,
        "error": error,
        "last_query": sql,
        "execution_time": execution_time,
    })


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
