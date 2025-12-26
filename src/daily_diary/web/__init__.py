"""Web UI for Daily Diary."""

import uvicorn


def run():
    """Run the web server."""
    uvicorn.run(
        "daily_diary.web.app:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )


__all__ = ["run"]
