"""SQLite analytics database for health diary data."""

from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Optional
import sqlite3
import json

import pandas as pd

from ..models.entry import DiaryEntry
from ..utils.config import get_settings


class AnalyticsDB:
    """
    SQLite database for storing and analyzing health diary data.
    
    Comprehensive schema with dedicated tables for each health domain:
    - daily_summary: Aggregated daily metrics for quick analysis
    - sleep: Detailed sleep data from Oura
    - activities: Individual exercise sessions from Strava
    - meals: Food intake with nutritional estimates
    - symptoms: Health symptoms with severity tracking
    - incidents: Notable health events
    - weather: Environmental conditions
    - vitals: Manual measurements (weight, BP, etc.)
    - medications: Medication tracking
    - supplements: Supplement intake
    - hydration: Fluid intake tracking
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        settings = get_settings()
        self.db_path = db_path or (settings.data_dir / "analytics.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
    
    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self.db_path),
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
            )
            # Enable foreign keys and WAL mode for better concurrency
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.row_factory = sqlite3.Row
            self._init_schema()
        return self._conn
    
    def _init_schema(self) -> None:
        """Initialize database schema with comprehensive health tables."""
        
        # ===== SLEEP TABLE =====
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS sleep (
                id TEXT PRIMARY KEY,
                entry_date TEXT NOT NULL,
                bedtime TEXT,
                wake_time TEXT,
                total_sleep_minutes INTEGER,
                rem_sleep_minutes INTEGER,
                deep_sleep_minutes INTEGER,
                light_sleep_minutes INTEGER,
                awake_minutes INTEGER,
                sleep_score INTEGER,
                efficiency_percent INTEGER,
                lowest_heart_rate REAL,
                average_heart_rate REAL,
                hrv_average REAL,
                hrv_max REAL,
                respiratory_rate REAL,
                body_temperature_delta REAL,
                readiness_score INTEGER,
                restless_periods INTEGER,
                source TEXT DEFAULT 'oura',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(entry_date, source)
            )
        """)
        
        # ===== ACTIVITIES TABLE =====
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS activities (
                id TEXT PRIMARY KEY,
                entry_date TEXT NOT NULL,
                activity_type TEXT NOT NULL,
                name TEXT,
                description TEXT,
                start_time TEXT,
                duration_minutes REAL,
                distance_km REAL,
                elevation_gain_m REAL,
                elevation_loss_m REAL,
                average_speed_kmh REAL,
                max_speed_kmh REAL,
                average_heart_rate REAL,
                max_heart_rate REAL,
                heart_rate_zones_json TEXT,
                average_power_watts REAL,
                max_power_watts REAL,
                normalized_power_watts REAL,
                intensity_factor REAL,
                training_stress_score REAL,
                average_cadence REAL,
                max_cadence REAL,
                suffer_score REAL,
                perceived_exertion INTEGER,
                calories_burned REAL,
                temperature_c REAL,
                humidity_percent INTEGER,
                wind_speed_kmh REAL,
                source TEXT DEFAULT 'strava',
                external_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # ===== MEALS TABLE =====
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS meals (
                id TEXT PRIMARY KEY,
                entry_date TEXT NOT NULL,
                meal_type TEXT NOT NULL,
                time_consumed TEXT,
                description TEXT NOT NULL,
                calories REAL,
                protein_g REAL,
                carbs_g REAL,
                fat_g REAL,
                fiber_g REAL,
                sugar_g REAL,
                sodium_mg REAL,
                water_ml REAL,
                contains_alcohol INTEGER DEFAULT 0,
                alcohol_units REAL,
                alcohol_type TEXT,
                contains_caffeine INTEGER DEFAULT 0,
                caffeine_mg REAL,
                trigger_foods TEXT,
                is_trigger_suspected INTEGER DEFAULT 0,
                nutrition_source TEXT DEFAULT 'estimated',
                estimation_confidence REAL,
                llm_reasoning TEXT,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # ===== SYMPTOMS TABLE =====
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS symptoms (
                id TEXT PRIMARY KEY,
                entry_date TEXT NOT NULL,
                symptom_type TEXT NOT NULL,
                symptom_subtype TEXT,
                custom_type TEXT,
                severity INTEGER NOT NULL,
                onset_time TEXT,
                end_time TEXT,
                duration_minutes INTEGER,
                body_location TEXT,
                custom_location TEXT,
                laterality TEXT,
                pain_character TEXT,
                with_nausea INTEGER DEFAULT 0,
                with_light_sensitivity INTEGER DEFAULT 0,
                with_sound_sensitivity INTEGER DEFAULT 0,
                with_aura INTEGER DEFAULT 0,
                with_visual_disturbance INTEGER DEFAULT 0,
                suspected_triggers TEXT,
                treatment_taken TEXT,
                treatment_effective INTEGER,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # ===== WEATHER TABLE =====
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS weather (
                id TEXT PRIMARY KEY,
                entry_date TEXT NOT NULL,
                recorded_at TEXT,
                temp_c REAL,
                temp_high_c REAL,
                temp_low_c REAL,
                feels_like_c REAL,
                pressure_hpa REAL,
                pressure_trend TEXT,
                pressure_change REAL,
                humidity_percent INTEGER,
                wind_speed_kmh REAL,
                wind_gust_kmh REAL,
                wind_direction_deg INTEGER,
                precipitation_mm REAL,
                precipitation_probability INTEGER,
                description TEXT,
                cloud_cover_percent INTEGER,
                visibility_km REAL,
                uv_index REAL,
                aqi INTEGER,
                pm25 REAL,
                pm10 REAL,
                sunrise TEXT,
                sunset TEXT,
                daylight_minutes INTEGER,
                moon_phase TEXT,
                source TEXT DEFAULT 'openweathermap',
                location_lat REAL,
                location_lon REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(entry_date, source)
            )
        """)
        
        # ===== VITALS TABLE =====
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS vitals (
                id TEXT PRIMARY KEY,
                entry_date TEXT NOT NULL,
                recorded_at TEXT,
                weight_kg REAL,
                body_fat_percent REAL,
                muscle_mass_kg REAL,
                waist_circumference_cm REAL,
                hip_circumference_cm REAL,
                systolic_bp INTEGER,
                diastolic_bp INTEGER,
                resting_heart_rate INTEGER,
                blood_glucose_mgdl REAL,
                glucose_timing TEXT,
                body_temperature_c REAL,
                blood_oxygen_percent INTEGER,
                respiratory_rate INTEGER,
                notes TEXT,
                source TEXT DEFAULT 'manual',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # ===== MEDICATIONS TABLE =====
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS medications (
                id TEXT PRIMARY KEY,
                entry_date TEXT NOT NULL,
                time_taken TEXT,
                name TEXT NOT NULL,
                dosage TEXT,
                dosage_mg REAL,
                form TEXT,
                purpose TEXT,
                for_symptom_id TEXT,
                effectiveness INTEGER,
                side_effects TEXT,
                is_prescription INTEGER DEFAULT 0,
                prescribing_doctor TEXT,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # ===== SUPPLEMENTS TABLE =====
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS supplements (
                id TEXT PRIMARY KEY,
                entry_date TEXT NOT NULL,
                time_taken TEXT,
                name TEXT NOT NULL,
                brand TEXT,
                dosage TEXT,
                dosage_amount REAL,
                dosage_unit TEXT,
                supplement_type TEXT,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # ===== HYDRATION TABLE =====
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS hydration (
                id TEXT PRIMARY KEY,
                entry_date TEXT NOT NULL,
                time_consumed TEXT,
                beverage_type TEXT NOT NULL,
                volume_ml REAL NOT NULL,
                contains_caffeine INTEGER DEFAULT 0,
                caffeine_mg REAL,
                contains_alcohol INTEGER DEFAULT 0,
                alcohol_units REAL,
                contains_sugar INTEGER DEFAULT 0,
                sugar_g REAL,
                sodium_mg REAL,
                potassium_mg REAL,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # ===== MEDITATION TABLE =====
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS meditation (
                id TEXT PRIMARY KEY,
                entry_date TEXT NOT NULL UNIQUE,
                duration_minutes INTEGER,
                activity_type TEXT DEFAULT 'meditation',
                notes TEXT,
                source TEXT DEFAULT 'manual',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # ===== INCIDENTS TABLE =====
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id TEXT PRIMARY KEY,
                entry_date TEXT NOT NULL,
                time_occurred TEXT,
                incident_type TEXT NOT NULL,
                custom_type TEXT,
                severity INTEGER,
                location TEXT,
                custom_location TEXT,
                description TEXT,
                duration_minutes INTEGER,
                suspected_cause TEXT,
                action_taken TEXT,
                medical_attention INTEGER DEFAULT 0,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # ===== DAILY SUMMARY TABLE =====
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_summary (
                entry_date TEXT PRIMARY KEY,
                overall_wellbeing INTEGER,
                energy_level INTEGER,
                stress_level INTEGER,
                mood TEXT,
                mood_score INTEGER,
                sleep_score INTEGER,
                total_sleep_minutes INTEGER,
                sleep_efficiency INTEGER,
                hrv_average REAL,
                activity_count INTEGER DEFAULT 0,
                total_activity_minutes REAL DEFAULT 0,
                total_distance_km REAL DEFAULT 0,
                total_elevation_m REAL DEFAULT 0,
                total_calories_burned REAL DEFAULT 0,
                meal_count INTEGER DEFAULT 0,
                total_calories REAL DEFAULT 0,
                total_protein_g REAL DEFAULT 0,
                total_carbs_g REAL DEFAULT 0,
                total_fat_g REAL DEFAULT 0,
                total_fiber_g REAL DEFAULT 0,
                total_water_ml REAL DEFAULT 0,
                total_caffeine_mg REAL DEFAULT 0,
                total_alcohol_units REAL DEFAULT 0,
                symptom_count INTEGER DEFAULT 0,
                worst_symptom_severity INTEGER,
                has_headache INTEGER DEFAULT 0,
                has_neuralgiaform INTEGER DEFAULT 0,
                incident_count INTEGER DEFAULT 0,
                temp_avg_c REAL,
                pressure_hpa REAL,
                pressure_change REAL,
                humidity_percent INTEGER,
                weight_kg REAL,
                resting_hr INTEGER,
                medication_count INTEGER DEFAULT 0,
                rescue_medication_used INTEGER DEFAULT 0,
                supplement_count INTEGER DEFAULT 0,
                morning_notes TEXT,
                evening_notes TEXT,
                general_notes TEXT,
                is_complete INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # ===== DAILY FACTORS TABLE =====
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_factors (
                entry_date TEXT PRIMARY KEY,
                cat_in_room INTEGER DEFAULT 0,
                cat_woke_me INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # ===== CORRELATION CACHE TABLE =====
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS correlation_cache (
                id TEXT PRIMARY KEY,
                computed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                days_analyzed INTEGER,
                start_date TEXT,
                end_date TEXT,
                factor_a TEXT,
                factor_b TEXT,
                correlation REAL,
                p_value REAL,
                sample_size INTEGER,
                is_significant INTEGER
            )
        """)
        
        # ===== CONSULTATIONS TABLE =====
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS consultations (
                id TEXT PRIMARY KEY,
                consultation_date TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                data_start_date TEXT,
                data_end_date TEXT,
                days_reviewed INTEGER,
                chief_complaint TEXT,
                summary TEXT,
                key_findings TEXT,
                patterns_identified TEXT,
                recommendations TEXT,
                triggers_discussed TEXT,
                follow_up_actions TEXT,
                message_count INTEGER DEFAULT 0,
                provider TEXT,
                conversation_json TEXT,
                user_notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes
        self._create_indexes()
        self.conn.commit()
    
    def _create_indexes(self) -> None:
        """Create indexes for performance."""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_sleep_date ON sleep(entry_date)",
            "CREATE INDEX IF NOT EXISTS idx_activities_date ON activities(entry_date)",
            "CREATE INDEX IF NOT EXISTS idx_meals_date ON meals(entry_date)",
            "CREATE INDEX IF NOT EXISTS idx_symptoms_date ON symptoms(entry_date)",
            "CREATE INDEX IF NOT EXISTS idx_symptoms_type ON symptoms(symptom_type)",
            "CREATE INDEX IF NOT EXISTS idx_weather_date ON weather(entry_date)",
            "CREATE INDEX IF NOT EXISTS idx_vitals_date ON vitals(entry_date)",
            "CREATE INDEX IF NOT EXISTS idx_medications_date ON medications(entry_date)",
            "CREATE INDEX IF NOT EXISTS idx_hydration_date ON hydration(entry_date)",
            "CREATE INDEX IF NOT EXISTS idx_daily_factors_date ON daily_factors(entry_date)",
        ]
        for idx in indexes:
            try:
                self.conn.execute(idx)
            except Exception:
                pass
    
    def execute(self, sql: str, params: list = None) -> sqlite3.Cursor:
        """Execute SQL and return cursor."""
        return self.conn.execute(sql, params or [])
    
    def upsert_entry(self, entry: DiaryEntry) -> None:
        """Insert or update a diary entry across all relevant tables."""
        import uuid
        from ..models.health import SymptomType
        
        entry_date = entry.entry_date.isoformat()
        
        # ===== SLEEP =====
        if entry.integrations.sleep:
            s = entry.integrations.sleep
            sleep_id = f"sleep_{entry_date}_oura"
            self.conn.execute("DELETE FROM sleep WHERE id = ?", [sleep_id])
            self.conn.execute("""
                INSERT INTO sleep (
                    id, entry_date, bedtime, wake_time,
                    total_sleep_minutes, rem_sleep_minutes, deep_sleep_minutes,
                    light_sleep_minutes, awake_minutes,
                    sleep_score, efficiency_percent,
                    lowest_heart_rate, average_heart_rate, hrv_average,
                    respiratory_rate, readiness_score, restless_periods, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                sleep_id, entry_date, 
                s.bedtime.isoformat() if s.bedtime else None, 
                s.wake_time.isoformat() if s.wake_time else None,
                s.total_sleep_minutes, s.rem_sleep_minutes, s.deep_sleep_minutes,
                s.light_sleep_minutes, s.awake_minutes,
                s.sleep_score, s.efficiency_percent,
                s.lowest_heart_rate, s.average_heart_rate, s.hrv_average,
                s.respiratory_rate, s.readiness_score, s.restless_periods, 'oura'
            ])
        
        # ===== ACTIVITIES =====
        self.conn.execute("""
                DELETE FROM activities WHERE entry_date = ? AND source != 'manual'
        """, [
            entry_date
        ])
        for activity in entry.integrations.activities or []:
            activity_id = activity.activity_id or str(uuid.uuid4())
            self.conn.execute("""
                INSERT INTO activities (
                    id, entry_date, activity_type, name, description, start_time,
                    duration_minutes, distance_km, elevation_gain_m,
                    average_speed_kmh, max_speed_kmh,
                    average_heart_rate, max_heart_rate,
                    average_power_watts, normalized_power_watts,
                    average_cadence, suffer_score, source, external_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                activity_id, entry_date, activity.activity_type, activity.name,
                activity.description, 
                activity.start_time.isoformat() if activity.start_time else None,
                activity.duration_minutes, activity.distance_km, activity.elevation_gain_m,
                activity.average_speed_kmh, activity.max_speed_kmh,
                activity.average_heart_rate, activity.max_heart_rate,
                activity.average_power_watts, activity.normalized_power_watts,
                activity.average_cadence, activity.suffer_score, 'strava', activity.activity_id
            ])
        
        # ===== WEATHER =====
        if entry.integrations.weather:
            w = entry.integrations.weather
            weather_id = f"weather_{entry_date}"
            self.conn.execute("DELETE FROM weather WHERE entry_date = ?", [entry_date])
            self.conn.execute("""
                INSERT INTO weather (
                    id, entry_date, temp_c, temp_high_c, temp_low_c,
                    pressure_hpa, pressure_change, humidity_percent, 
                    precipitation_mm, wind_speed_kmh, description, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                weather_id, entry_date, w.temp_avg_c, w.temp_high_c, w.temp_low_c,
                w.pressure_hpa, w.pressure_change_hpa, w.humidity_percent,
                w.precipitation_mm, w.wind_speed_kmh, w.description, 'open-meteo'
            ])
        
        # ===== MEALS =====
        # Meals are managed separately via add_meal_with_nutrition
        
        # ===== SYMPTOMS =====
        self.conn.execute("DELETE FROM symptoms WHERE entry_date = ?", [entry_date])
        for symptom in entry.symptoms:
            symptom_id = str(uuid.uuid4())
            self.conn.execute("""
                INSERT INTO symptoms (
                    id, entry_date, symptom_type, custom_type, severity,
                    onset_time, duration_minutes, body_location, custom_location, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                symptom_id, entry_date, symptom.type.value, symptom.custom_type,
                symptom.severity.value, 
                symptom.onset_time.isoformat() if symptom.onset_time else None, 
                symptom.duration_minutes,
                symptom.location.value if symptom.location else None,
                symptom.custom_location, symptom.notes
            ])
        
        # ===== INCIDENTS =====
        self.conn.execute("DELETE FROM incidents WHERE entry_date = ?", [entry_date])
        for incident in entry.incidents:
            incident_id = str(uuid.uuid4())
            self.conn.execute("""
                INSERT INTO incidents (
                    id, entry_date, incident_type, custom_type, severity,
                    location, custom_location, description, time_occurred
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                incident_id, entry_date, incident.type.value, incident.custom_type,
                incident.severity.value, 
                incident.location.value if incident.location else None,
                incident.custom_location, incident.description, 
                incident.time_occurred.isoformat() if incident.time_occurred else None
            ])
        
        # ===== MEDICATIONS =====
        self.conn.execute("DELETE FROM medications WHERE entry_date = ?", [entry_date])
        for med in entry.medications:
            med_id = str(uuid.uuid4())
            self.conn.execute("""
                INSERT INTO medications (
                    id, entry_date, name, dosage, form, time_taken, purpose, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                med_id, entry_date, med.name, med.dosage,
                med.form.value if med.form else None,
                med.time_taken.isoformat() if med.time_taken else None, 
                med.reason, med.notes
            ])
        
        # ===== SUPPLEMENTS =====
        self.conn.execute("DELETE FROM supplements WHERE entry_date = ?", [entry_date])
        for supp in entry.supplements:
            supp_id = str(uuid.uuid4())
            self.conn.execute("""
                INSERT INTO supplements (
                    id, entry_date, name, dosage, time_taken, notes
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, [
                supp_id, entry_date, supp.name, supp.dosage,
                supp.time_taken.isoformat() if supp.time_taken else None, 
                supp.notes
            ])
        
        # ===== DAILY SUMMARY =====
        self._update_daily_summary(entry)
        self.conn.commit()
    
    def _update_daily_summary(self, entry: DiaryEntry) -> None:
        """Update the daily summary table with aggregated data."""
        from ..models.health import SymptomType
        
        entry_date = entry.entry_date.isoformat()
        
        activities = entry.integrations.activities or []
        total_activity_mins = sum(a.duration_minutes for a in activities)
        total_distance = sum(a.distance_km or 0 for a in activities)
        total_elevation = sum(a.elevation_gain_m or 0 for a in activities)
        
        worst_severity = max((s.severity.value for s in entry.symptoms), default=None)
        has_headache = any(
            s.type in (SymptomType.HEADACHE, SymptomType.HEADACHE_NEURALGIAFORM)
            for s in entry.symptoms
        )
        has_neuralgiaform = any(
            s.type == SymptomType.HEADACHE_NEURALGIAFORM
            for s in entry.symptoms
        )
        
        total_alcohol = sum(m.alcohol_units or 0 for m in entry.meals if m.contains_alcohol)
        
        s = entry.integrations.sleep
        w = entry.integrations.weather
        
        self.conn.execute("""
            INSERT OR REPLACE INTO daily_summary (
                entry_date,
                overall_wellbeing, energy_level, stress_level, mood,
                sleep_score, total_sleep_minutes, sleep_efficiency, hrv_average,
                activity_count, total_activity_minutes, total_distance_km, total_elevation_m,
                meal_count, total_alcohol_units,
                symptom_count, worst_symptom_severity, has_headache, has_neuralgiaform,
                incident_count,
                temp_avg_c, pressure_hpa, humidity_percent,
                morning_notes, evening_notes, general_notes,
                is_complete, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            entry_date,
            entry.overall_wellbeing, entry.energy_level, entry.stress_level, entry.mood,
            s.sleep_score if s else None, s.total_sleep_minutes if s else None,
            s.efficiency_percent if s else None, s.hrv_average if s else None,
            len(activities), total_activity_mins, total_distance, total_elevation,
            len(entry.meals), total_alcohol,
            len(entry.symptoms), worst_severity, 1 if has_headache else 0, 1 if has_neuralgiaform else 0,
            len(entry.incidents),
            w.temp_avg_c if w else None, w.pressure_hpa if w else None,
            w.humidity_percent if w else None,
            entry.morning_notes, entry.evening_notes, entry.general_notes,
            1 if entry.is_complete else 0, datetime.now().isoformat()
        ])
    
    def add_meal_with_nutrition(
        self,
        entry_date: date,
        meal_type: str,
        description: str,
        nutrition: dict,
        time_consumed: Optional[time] = None,
        notes: Optional[str] = None,
    ) -> str:
        """Add a meal with nutritional information."""
        import uuid
        
        meal_id = str(uuid.uuid4())
        
        self.conn.execute("""
            INSERT INTO meals (
                id, entry_date, meal_type, time_consumed, description,
                calories, protein_g, carbs_g, fat_g, fiber_g, sugar_g, sodium_mg,
                water_ml, caffeine_mg, contains_caffeine, contains_alcohol, alcohol_units,
                nutrition_source, estimation_confidence, llm_reasoning, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            meal_id, entry_date.isoformat(), meal_type, 
            time_consumed.isoformat() if time_consumed else None, 
            description,
            nutrition.get('calories'), nutrition.get('protein_g'), nutrition.get('carbs_g'),
            nutrition.get('fat_g'), nutrition.get('fiber_g'), nutrition.get('sugar_g'),
            nutrition.get('sodium_mg'), nutrition.get('water_ml'),
            nutrition.get('caffeine_mg'), 1 if nutrition.get('caffeine_mg', 0) > 0 else 0,
            1 if nutrition.get('alcohol_units', 0) > 0 else 0, nutrition.get('alcohol_units'),
            nutrition.get('source', 'estimated'), nutrition.get('confidence'),
            nutrition.get('reasoning'), notes
        ])
        
        self.conn.commit()
        return meal_id
    
    def save_vitals(
        self,
        entry_date: date,
        weight_kg: Optional[float] = None,
        body_fat_percent: Optional[float] = None,
        waist_circumference_cm: Optional[float] = None,
        hip_circumference_cm: Optional[float] = None,
        systolic_bp: Optional[int] = None,
        diastolic_bp: Optional[int] = None,
        resting_heart_rate: Optional[int] = None,
        blood_glucose_mgdl: Optional[float] = None,
        glucose_timing: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> str:
        """Save or update vitals for a date."""
        import uuid
        
        entry_date_str = entry_date.isoformat()
        
        # Check if vitals exist for this date
        existing = self.conn.execute(
            "SELECT id FROM vitals WHERE entry_date = ?",
            [entry_date_str]
        ).fetchone()
        
        if existing:
            # Update existing record
            self.conn.execute("""
                UPDATE vitals SET
                    weight_kg = COALESCE(?, weight_kg),
                    body_fat_percent = COALESCE(?, body_fat_percent),
                    waist_circumference_cm = COALESCE(?, waist_circumference_cm),
                    hip_circumference_cm = COALESCE(?, hip_circumference_cm),
                    systolic_bp = COALESCE(?, systolic_bp),
                    diastolic_bp = COALESCE(?, diastolic_bp),
                    resting_heart_rate = COALESCE(?, resting_heart_rate),
                    blood_glucose_mgdl = COALESCE(?, blood_glucose_mgdl),
                    glucose_timing = COALESCE(?, glucose_timing),
                    notes = COALESCE(?, notes)
                WHERE entry_date = ?
            """, [
                weight_kg, body_fat_percent, waist_circumference_cm, hip_circumference_cm,
                systolic_bp, diastolic_bp, resting_heart_rate,
                blood_glucose_mgdl, glucose_timing, notes, entry_date_str
            ])
            vital_id = existing[0]
        else:
            # Insert new record
            vital_id = str(uuid.uuid4())
            self.conn.execute("""
                INSERT INTO vitals (
                    id, entry_date, weight_kg, body_fat_percent,
                    waist_circumference_cm, hip_circumference_cm,
                    systolic_bp, diastolic_bp, resting_heart_rate,
                    blood_glucose_mgdl, glucose_timing, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                vital_id, entry_date_str, weight_kg, body_fat_percent,
                waist_circumference_cm, hip_circumference_cm,
                systolic_bp, diastolic_bp, resting_heart_rate,
                blood_glucose_mgdl, glucose_timing, notes
            ])
        
        self.conn.commit()
        return vital_id
    
    def get_vitals(self, entry_date: date) -> Optional[dict]:
        """Get vitals for a specific date."""
        result = self.conn.execute(
            "SELECT * FROM vitals WHERE entry_date = ?",
            [entry_date.isoformat()]
        ).fetchone()
        
        if result:
            return dict(result)
        return None
    
    def get_vitals_history(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """Get vitals history as DataFrame."""
        query = "SELECT * FROM vitals"
        conditions = []
        params = []
        
        if start_date:
            conditions.append("entry_date >= ?")
            params.append(start_date.isoformat())
        if end_date:
            conditions.append("entry_date <= ?")
            params.append(end_date.isoformat())
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY entry_date DESC"
        
        return pd.read_sql(query, self.conn, params=params)
    
    def save_meditation(
        self,
        entry_date: date,
        duration_minutes: Optional[int] = None,
        activity_type: str = "meditation",
        notes: Optional[str] = None,
    ) -> str:
        """Save or update meditation for a date."""
        import uuid
        
        entry_date_str = entry_date.isoformat()
        
        # Check if meditation exists for this date
        existing = self.conn.execute(
            "SELECT id FROM meditation WHERE entry_date = ?",
            [entry_date_str]
        ).fetchone()
        
        if existing:
            # Update existing record
            self.conn.execute("""
                UPDATE meditation SET
                    duration_minutes = ?,
                    activity_type = ?,
                    notes = ?,
                    updated_at = ?
                WHERE entry_date = ?
            """, [
                duration_minutes, activity_type, notes,
                datetime.now().isoformat(), entry_date_str
            ])
            meditation_id = existing[0]
        else:
            # Insert new record
            meditation_id = str(uuid.uuid4())
            self.conn.execute("""
                INSERT INTO meditation (
                    id, entry_date, duration_minutes, activity_type, notes
                ) VALUES (?, ?, ?, ?, ?)
            """, [
                meditation_id, entry_date_str, duration_minutes, activity_type, notes
            ])
        
        self.conn.commit()
        return meditation_id
    
    def get_meditation(self, entry_date: date) -> Optional[dict]:
        """Get meditation for a specific date."""
        result = self.conn.execute(
            "SELECT * FROM meditation WHERE entry_date = ?",
            [entry_date.isoformat()]
        ).fetchone()
        
        if result:
            return dict(result)
        return None
    
    def get_meditation_history(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """Get meditation history as DataFrame."""
        query = "SELECT * FROM meditation"
        conditions = []
        params = []
        
        if start_date:
            conditions.append("entry_date >= ?")
            params.append(start_date.isoformat())
        if end_date:
            conditions.append("entry_date <= ?")
            params.append(end_date.isoformat())
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY entry_date DESC"
        
        return pd.read_sql(query, self.conn, params=params)
    
    def save_manual_activity(
        self,
        entry_date: date,
        activity_type: str,
        duration_minutes: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> Optional[str]:
        """Save or update a manual activity (boxing, weightlifting, etc.) for a date."""
        import uuid

        if not duration_minutes:
            # Delete if exists and no duration provided
            self.conn.execute(
                "DELETE FROM activities WHERE entry_date = ? AND activity_type = ? AND source = 'manual'",
                [entry_date.isoformat(), activity_type]
            )
            self.conn.commit()
            return None

        entry_date_str = entry_date.isoformat()
        
        # Check if manual activity of this type exists for this date
        existing = self.conn.execute(
            "SELECT id FROM activities WHERE entry_date = ? AND activity_type = ? AND source = 'manual'",
            [entry_date_str, activity_type]
        ).fetchone()
        
        if existing:
            # Update existing record
            self.conn.execute("""
                UPDATE activities SET
                    duration_minutes = ?,
                    description = ?,
                    updated_at = ?
                WHERE id = ?
            """, [
                duration_minutes, notes,
                datetime.now().isoformat(), existing[0]
            ])
            activity_id = existing[0]
        else:
            # Insert new record
            activity_id = str(uuid.uuid4())
            self.conn.execute("""
                INSERT INTO activities (
                    id, entry_date, activity_type, name, duration_minutes, 
                    description, source
                ) VALUES (?, ?, ?, ?, ?, ?, 'manual')
            """, [
                activity_id, entry_date_str, activity_type, 
                activity_type.title(), duration_minutes, notes
            ])

        self.conn.commit()
        return activity_id
    
    def get_manual_activities(self, entry_date: date) -> dict:
        """Get manual activities for a specific date as a dict keyed by activity_type."""
        results = self.conn.execute(
            "SELECT * FROM activities WHERE entry_date = ? AND source = 'manual'",
            [entry_date.isoformat()]
        ).fetchall()
        
        activities = {}
        for row in results:
            row_dict = dict(row)
            activities[row_dict['activity_type']] = row_dict
        return activities
    
    def get_daily_summary_df(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """Get daily summary data as a DataFrame for analysis."""
        query = "SELECT * FROM daily_summary"
        conditions = []
        params = []
        
        if start_date:
            conditions.append("entry_date >= ?")
            params.append(start_date.isoformat())
        if end_date:
            conditions.append("entry_date <= ?")
            params.append(end_date.isoformat())
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY entry_date"
        
        return pd.read_sql(query, self.conn, params=params)
    
    def sync_quick_log(self, entry_date: date, quick_log: dict, totals: dict) -> None:
        """Sync quick_log data to SQLite."""
        entry_date_str = entry_date.isoformat()
        cat_in_room = 1 if quick_log.get('cat_in_room', 0) == 1 else 0
        cat_woke_me = 1 if quick_log.get('cat_woke_me', 0) == 1 else 0
        
        self.conn.execute("""
            INSERT OR REPLACE INTO daily_factors (
                entry_date, cat_in_room, cat_woke_me, updated_at
            ) VALUES (?, ?, ?, ?)
        """, [entry_date_str, cat_in_room, cat_woke_me, datetime.now().isoformat()])
        
        caffeine_mg = totals.get('total_caffeine_mg', 0)
        alcohol_units = totals.get('total_alcohol_units', 0)
        
        existing = self.conn.execute(
            "SELECT 1 FROM daily_summary WHERE entry_date = ?", 
            [entry_date_str]
        ).fetchone()
        
        if existing:
            self.conn.execute("""
                UPDATE daily_summary SET
                    total_caffeine_mg = ?,
                    total_alcohol_units = ?,
                    updated_at = ?
                WHERE entry_date = ?
            """, [caffeine_mg, alcohol_units, datetime.now().isoformat(), entry_date_str])
        else:
            self.conn.execute("""
                INSERT INTO daily_summary (entry_date, total_caffeine_mg, total_alcohol_units, updated_at)
                VALUES (?, ?, ?, ?)
            """, [entry_date_str, caffeine_mg, alcohol_units, datetime.now().isoformat()])
        
        self.conn.commit()
    
    def get_analysis_data(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """Get comprehensive daily data for correlation analysis."""
        query = """
            SELECT 
                ds.*,
                df.cat_in_room,
                df.cat_woke_me,
                COALESCE(n.total_calories, 0) as nutrition_calories,
                COALESCE(n.total_protein_g, 0) as nutrition_protein_g,
                COALESCE(n.meal_caffeine_mg, 0) as meal_caffeine_mg
            FROM daily_summary ds
            LEFT JOIN daily_factors df ON ds.entry_date = df.entry_date
            LEFT JOIN (
                SELECT 
                    entry_date,
                    SUM(calories) as total_calories,
                    SUM(protein_g) as total_protein_g,
                    SUM(caffeine_mg) as meal_caffeine_mg
                FROM meals
                GROUP BY entry_date
            ) n ON ds.entry_date = n.entry_date
        """
        conditions = []
        params = []
        
        if start_date:
            conditions.append("ds.entry_date >= ?")
            params.append(start_date.isoformat())
        if end_date:
            conditions.append("ds.entry_date <= ?")
            params.append(end_date.isoformat())
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY ds.entry_date"
        
        return pd.read_sql(query, self.conn, params=params)
    
    def get_nutrition_summary(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """Get daily nutrition totals."""
        query = """
            SELECT 
                entry_date,
                COUNT(*) as meal_count,
                SUM(calories) as total_calories,
                SUM(protein_g) as total_protein_g,
                SUM(carbs_g) as total_carbs_g,
                SUM(fat_g) as total_fat_g,
                SUM(fiber_g) as total_fiber_g,
                SUM(caffeine_mg) as total_caffeine_mg,
                SUM(alcohol_units) as total_alcohol_units
            FROM meals
        """
        conditions = []
        params = []
        
        if start_date:
            conditions.append("entry_date >= ?")
            params.append(start_date.isoformat())
        if end_date:
            conditions.append("entry_date <= ?")
            params.append(end_date.isoformat())
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " GROUP BY entry_date ORDER BY entry_date"
        
        return pd.read_sql(query, self.conn, params=params)
    
    def get_sleep_trends(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """Get sleep data trends."""
        query = """
            SELECT 
                entry_date,
                sleep_score,
                total_sleep_minutes,
                deep_sleep_minutes,
                rem_sleep_minutes,
                light_sleep_minutes,
                efficiency_percent,
                hrv_average,
                lowest_heart_rate,
                respiratory_rate
            FROM sleep
        """
        conditions = []
        params = []
        
        if start_date:
            conditions.append("entry_date >= ?")
            params.append(start_date.isoformat())
        if end_date:
            conditions.append("entry_date <= ?")
            params.append(end_date.isoformat())
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY entry_date"
        
        return pd.read_sql(query, self.conn, params=params)
    
    def query(self, sql: str, params: list = None) -> pd.DataFrame:
        """Execute arbitrary SQL query and return DataFrame."""
        return pd.read_sql(sql, self.conn, params=params or [])
    
    def get_table_info(self) -> pd.DataFrame:
        """Get information about all tables."""
        tables = pd.read_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name",
            self.conn
        )
        
        results = []
        for table_name in tables['name']:
            cols = self.conn.execute(f"PRAGMA table_info({table_name})").fetchall()
            for col in cols:
                results.append({
                    'table_name': table_name,
                    'column_name': col[1],
                    'data_type': col[2],
                    'is_nullable': 'YES' if col[3] == 0 else 'NO'
                })
        
        return pd.DataFrame(results)
    
    def get_schema_summary(self) -> str:
        """Get a human-readable summary of all tables and columns."""
        tables = pd.read_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name",
            self.conn
        )
        
        result = []
        for table_name in tables['name']:
            cols = self.conn.execute(f"PRAGMA table_info({table_name})").fetchall()
            
            result.append(f"\n=== {table_name.upper()} ===")
            for col in cols:
                result.append(f"  {col[1]}: {col[2]}")
        
        return "\n".join(result)
    
    def save_consultation(
        self,
        consultation_id: str,
        consultation_date: date,
        started_at: datetime,
        ended_at: datetime,
        days_reviewed: int,
        chief_complaint: Optional[str],
        summary: str,
        key_findings: Optional[str],
        patterns_identified: Optional[str],
        recommendations: Optional[str],
        triggers_discussed: Optional[str],
        follow_up_actions: Optional[str],
        message_count: int,
        provider: str,
        conversation_json: str,
    ) -> None:
        """Save a consultation record."""
        data_end = consultation_date
        data_start = consultation_date - timedelta(days=days_reviewed)
        
        self.conn.execute("""
            INSERT INTO consultations (
                id, consultation_date, started_at, ended_at,
                data_start_date, data_end_date, days_reviewed,
                chief_complaint, summary, key_findings, patterns_identified,
                recommendations, triggers_discussed, follow_up_actions,
                message_count, provider, conversation_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            consultation_id, consultation_date.isoformat(), 
            started_at.isoformat(), ended_at.isoformat(),
            data_start.isoformat(), data_end.isoformat(), days_reviewed,
            chief_complaint, summary, key_findings, patterns_identified,
            recommendations, triggers_discussed, follow_up_actions,
            message_count, provider, conversation_json
        ])
        self.conn.commit()
    
    def get_consultations(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 20,
    ) -> pd.DataFrame:
        """Get consultation records."""
        query = "SELECT * FROM consultations"
        conditions = []
        params = []
        
        if start_date:
            conditions.append("consultation_date >= ?")
            params.append(start_date.isoformat())
        if end_date:
            conditions.append("consultation_date <= ?")
            params.append(end_date.isoformat())
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        
        return pd.read_sql(query, self.conn, params=params)
    
    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.commit()
            self._conn.close()
            self._conn = None
    
    def __enter__(self) -> "AnalyticsDB":
        return self
    
    def __exit__(self, *args) -> None:
        self.close()
