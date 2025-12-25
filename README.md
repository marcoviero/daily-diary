# Daily Health Diary

Personal health tracking application with automated data integration.

## Features

- **Symptom tracking**: Log pain, headaches, and other symptoms with severity scales
- **Automatic data collection**: Weather, Strava activities, Oura sleep data
- **Voice transcription**: Dictate diary entries via Whisper API
- **Smart prompting**: Interactive daily entry flow with contextual questions
- **Local storage**: TinyDB JSON storage (your health data stays on your machine)

## Setup

1. Clone the repository
2. Install dependencies:
   ```bash
   uv sync
   ```
3. Copy `.env.example` to `.env` and add your API keys
4. Run the CLI:
   ```bash
   uv run diary
   ```

## Required API Keys

| Service | URL | Purpose |
|---------|-----|---------|
| OpenWeatherMap | https://openweathermap.org/api | Weather data |
| Strava | https://www.strava.com/settings/api | Exercise activities |
| Oura | https://cloud.ouraring.com/personal-access-tokens | Sleep data |
| OpenAI | https://platform.openai.com/api-keys | Voice transcription |

## Usage

```bash
# Start a new diary entry for today
uv run diary new

# View recent entries
uv run diary list

# Search entries
uv run diary search "headache"
```

## Project Structure

```
src/daily_diary/
├── cli.py              # Command-line interface
├── clients/            # API clients (Weather, Strava, Oura)
├── models/             # Data models (DiaryEntry, Symptom, etc.)
├── services/           # Business logic (prompting, transcription)
└── utils/              # Helpers (config, date handling)
```
