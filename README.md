# Daily Health Diary

Personal health tracking application with automated data integration and correlation analysis.

## Features

- **Symptom tracking**: Log pain, headaches, and other symptoms with severity scales
- **Automatic data collection**: Weather, Strava activities, Oura sleep data
- **Voice transcription**: Dictate diary entries via Whisper API
- **Smart prompting**: Interactive daily entry flow with contextual questions
- **Web interface**: Beautiful UI for logging and reviewing entries
- **Correlation analysis**: Find relationships between symptoms and triggers
- **Local storage**: TinyDB JSON storage (your health data stays on your machine)

## Quick Start

```bash
# Install dependencies
uv sync

# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys

# Start the web interface
uv run diary web

# Open http://localhost:8000 in your browser
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `diary web` | Start the web interface (http://localhost:8000) |
| `diary new` | Start full daily entry with CLI prompts |
| `diary symptom` | Quick symptom logging |
| `diary show 2024-12-25` | View a specific day |
| `diary list -n 14` | List last 14 days |
| `diary search "headache"` | Search entries |
| `diary fetch` | Manually fetch integration data |
| `diary transcribe voice.m4a` | Transcribe audio to notes |
| `diary status` | Show which integrations are configured |

## Required API Keys

| Service | URL | Purpose |
|---------|-----|---------|
| OpenWeatherMap | https://openweathermap.org/api | Weather & pressure data |
| Strava | https://www.strava.com/settings/api | Exercise activities |
| Oura | https://cloud.ouraring.com/personal-access-tokens | Sleep & HRV data |
| OpenAI | https://platform.openai.com/api-keys | Voice transcription |

## Web Interface

The web UI provides:

- **Dashboard**: Quick access to new entries and analysis
- **Entry List**: Table view with weather, sleep, activity, and symptoms
- **Entry Form**: Edit entries with auto-fetched data
- **Analysis Dashboard**: 
  - Summary statistics
  - Correlation analysis (Pearson r with p-values)
  - Pattern detection (day-of-week, weekend effects)
  - Interactive charts (Plotly)

## Analysis Features

The analysis engine looks for correlations between symptoms and:
- **Weather**: Barometric pressure, temperature, humidity
- **Sleep**: Score, duration, HRV, heart rate
- **Exercise**: Duration, intensity, elevation
- **Diet**: Alcohol, caffeine consumption
- **Temporal patterns**: Day of week, weekend effects
- **Lagged effects**: Previous day's activities

## Project Structure

```
src/daily_diary/
├── cli.py              # Typer CLI
├── models/             # Pydantic data models
├── clients/            # API clients (Weather, Strava, Oura)
├── services/           # Business logic
│   ├── storage.py      # TinyDB persistence
│   ├── analysis.py     # Correlation & pattern detection
│   ├── prompting.py    # Interactive CLI prompts
│   └── transcription.py# Whisper voice-to-text
└── web/                # FastAPI web interface
    ├── app.py          # FastAPI application
    ├── routes/         # API and page routes
    ├── templates/      # Jinja2 HTML templates
    └── static/         # CSS/JS assets
```

## Privacy

Your health data stays on your machine. The only external calls are:
- Weather API (location-based weather data)
- Strava API (your activity data)
- Oura API (your sleep data)
- OpenAI Whisper (audio transcription only)

No data is sent to Anthropic, and the database stays local in the `data/` directory.
