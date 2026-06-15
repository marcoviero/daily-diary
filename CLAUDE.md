# CLAUDE.md — Daily Diary

Personal health diary for tracking diet, symptoms, and lifestyle factors to help diagnose chronic conditions — primarily neuralgiform (TN-type) headaches and knee pain. Uses LLMs for nutrition estimation, diary parsing, and an AI health advisor.

---

## Running the project

```bash
# Install dependencies
uv sync

# CLI commands
uv run diary log-meal "burger and fries" --type lunch
uv run diary log-meal "coffee" --type snack --date 2026-06-10
uv run diary parse-entry notes.txt          # Parse voice-note transcription
uv run diary sync-strava                    # Pull Strava activities
uv run diary sync-oura                      # Pull Oura sleep data

# Web UI (http://localhost:8000)
uv run diary-web

# Linting
uv run ruff check src/
```

---

## Architecture

### Two-layer data storage

| Layer | Technology | What lives here |
|-------|-----------|-----------------|
| Primary diary | TinyDB (JSON in `data/`) | Structured diary entries: symptoms, medications, meals-from-diary, notes, integrations |
| Analytics | SQLite (`data/analytics.db`) | Denormalized tables for fast analysis: meals, vitals, activities, symptoms, daily_summary, correlations |

`DiaryStorage` (TinyDB) is the system of record. `AnalyticsDB` is a derived, queryable copy. `upsert_entry()` in `database.py` syncs a `DiaryEntry` into SQLite. These two layers must stay in sync — never write to SQLite directly for data that belongs in the diary.

### Key service files

| File | Role |
|------|------|
| `services/nutrition.py` | LLM nutrition estimator (Claude → OpenAI → heuristic fallback). Has `find_cached_meal_nutrition()` to skip LLM on repeat meals. `max_tokens=2000` — keep it high to avoid truncated JSON. |
| `services/diary_parser.py` | Parses free-text voice notes into structured `DiaryEntry` objects via Claude |
| `services/advisor.py` | Multi-turn AI health advisor; loads full health context (from both TinyDB + SQLite) on `start_consultation()`. Uses `start_str`/`end_str` ISO strings for `pd.read_sql` params — not bare `date` objects. |
| `services/analysis.py` | Pearson correlations, lag correlations, fitness metrics (CTL/ATL/TSB), medication effectiveness |
| `services/database.py` | `AnalyticsDB` — SQLite wrapper with schema init, upsert, and all read methods |
| `clients/strava.py` | Strava OAuth refresh + activity fetch |
| `clients/oura.py` | Oura ring sleep/HRV fetch |

### Web layer

FastAPI app in `web/app.py`. SQL explorer lives there directly (not a router). All other routes are in `web/routes/`. Templates use Jinja2 + Tailwind (dark slate theme).

---

## Environment variables (`.env`)

```
ANTHROPIC_API_KEY=...          # Required: nutrition, diary parsing, advisor, SQL AI
OPENAI_API_KEY=...             # Optional: fallback nutrition (currently over quota)

STRAVA_CLIENT_ID=...
STRAVA_CLIENT_SECRET=...
STRAVA_REFRESH_TOKEN=...       # Refreshed automatically; update if it rotates

OURA_ACCESS_TOKEN=...          # Personal Access Token (simpler than OAuth2)

OPENWEATHER_API_KEY=...        # Or leave blank — Open-Meteo is used as free fallback

DEFAULT_LATITUDE=45.5152       # Portland, OR
DEFAULT_LONGITUDE=-122.6784
```

`.env` and `data/` are gitignored (contain PHI). Never commit them.

---

## LLM models in use

| Service | Model | Rationale |
|---------|-------|-----------|
| Nutrition estimator | `claude-sonnet-4-6` | Structured JSON with step-by-step reasoning |
| Diary parser | `claude-sonnet-4-6` | Complex free-text → structured object |
| Health advisor | `claude-opus-4-8` | Multi-turn medical reasoning |
| SQL AI suggest | `claude-sonnet-4-6` | Short schema-aware query generation |

**Model naming rule**: use the alias form with no date suffix (`claude-sonnet-4-6`, not `claude-sonnet-4-6-20251114`). Anthropic deprecates old models without notice; when updating, use `claude-api migrate` to find replacements.

---

## Data model — symptoms

`SymptomType` enum in `models/health.py`:
- `HEADACHE_NEURALGIAFORM` — neuralgiform / TN-type headache (the primary target)
- `HEADACHE` — regular headache
- `JOINT_PAIN` at `KNEE_LEFT` / `KNEE_RIGHT` — knee pain

`daily_summary` table has `has_headache` and `has_neuralgiaform` columns. **It does not yet have `has_knee_pain` or `knee_severity`** — these need to be added (via ALTER TABLE in `_init_schema`) before the analysis tab can show knee correlations.

---

## Exercise / activities

Activities land in the `activities` SQLite table from two sources:
- **Strava sync** (`clients/strava.py`) — GPS activities (running, cycling, hiking)
- **Manual log** — `database.save_manual_activity()`, MET-based calorie estimation

Current MET table in `database.estimate_calories_burned()` includes boxing and weightlifting. **Planned additions: tennis, snowboarding, jump rope.** When adding a new sport, update:
1. The MET values dict in `estimate_calories_burned()`
2. The quick-log form in `templates/entries/form.html` (activity type picker)

Apple Health import may come later (no Apple Watch yet); design `save_manual_activity()` to be source-agnostic when that time comes.

---

## Planned upcoming work

### Analysis tab — per-symptom tabbed switcher

The dashboard hardcodes `target='has_neuralgiaform'` in every `AnalysisService` call. The goal is a tab/dropdown that switches between symptom targets:

1. **Add columns to `daily_summary`**: `has_knee_pain INTEGER DEFAULT 0`, `knee_severity INTEGER` — populate in `_update_daily_summary()` by checking symptoms for `JOINT_PAIN` at knee locations.
2. **Extend `_entry_to_row()`** in `analysis.py` with `has_knee_pain` and `knee_severity`.
3. **Update `analysis_dashboard` route** to accept a `target` query param (default `neuralgiaform`) and pass it to all `AnalysisService` calls.
4. **Add a tab switcher** in `dashboard.html` — tabs for Headache+, Knee, Regular Headache. Each tab reloads with `?target=X&days=Y`.
5. Consider an LLM-written narrative summary per tab (one paragraph from the advisor with the correlation data as context).

### Exercise integration — new activity types

Add `tennis`, `snowboarding`, `jumprope` to `estimate_calories_burned()` MET table and to the manual log form. Tennis ≈ 7.0 MET, snowboarding ≈ 5.3 MET, jump rope ≈ 10.0 MET.

Future: Apple Health import — plan as a new `source='apple_health'` in the activities table; `save_manual_activity()` already accepts a `source` param.

---

## Key pitfalls

- **`pd.read_sql` date params**: SQLite stores dates as ISO strings. Pass `date.isoformat()` strings, not bare `datetime.date` objects. In `advisor.py` this is done via `start_str`/`end_str`.
- **Two-layer sync**: `AnalyticsDB.upsert_entry()` is the only sanctioned write path from diary entries to SQLite. Direct SQLite inserts for diary data will drift from TinyDB.
- **Nutrition `max_tokens`**: Keep at `2000`. The step-by-step reasoning field is verbose; `800` causes truncated JSON and silent fallback to heuristics.
- **Meal cache**: `find_cached_meal_nutrition()` matches on exact `description` + `meal_type` (case-insensitive). The cache is only used for `nutrition_source='llm'` rows. Heuristic results are not cached.
- **Branch convention**: Feature branches named `<topic>-N` (e.g., `upgrade-model-1`); commit messages prefixed `[branch-name]`.
- **`data/` is gitignored**: `analytics.db`, backups, and all JSON diary files stay local. Never add them.
