"""DuckDB analytics database for health diary data."""

from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd

from ..models.entry import DiaryEntry
from ..utils.config import get_settings


class AnalyticsDB:
    """
    DuckDB database for storing and analyzing health diary data.
    
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
        self.db_path = db_path or (settings.data_dir / "analytics.duckdb")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[duckdb.DuckDBPyConnection] = None
    
    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            self._conn = duckdb.connect(str(self.db_path))
            self._init_schema()
        return self._conn
    
    def _init_schema(self) -> None:
        """Initialize database schema with comprehensive health tables."""
        
        # ===== SLEEP TABLE =====
        # Detailed sleep data from Oura Ring
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS sleep (
                id VARCHAR PRIMARY KEY,
                entry_date DATE NOT NULL,
                
                -- Timing
                bedtime TIMESTAMP,
                wake_time TIMESTAMP,
                
                -- Duration (minutes)
                total_sleep_minutes INTEGER,
                rem_sleep_minutes INTEGER,
                deep_sleep_minutes INTEGER,
                light_sleep_minutes INTEGER,
                awake_minutes INTEGER,
                
                -- Quality scores (0-100)
                sleep_score INTEGER,
                efficiency_percent INTEGER,
                
                -- Physiological
                lowest_heart_rate FLOAT,
                average_heart_rate FLOAT,
                hrv_average FLOAT,
                hrv_max FLOAT,
                respiratory_rate FLOAT,
                body_temperature_delta FLOAT,
                
                -- Readiness
                readiness_score INTEGER,
                
                -- Sleep stages count
                restless_periods INTEGER,
                
                -- Source tracking
                source VARCHAR DEFAULT 'oura',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                UNIQUE(entry_date, source)
            )
        """)
        
        # ===== ACTIVITIES TABLE =====
        # Exercise and movement data from Strava
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS activities (
                id VARCHAR PRIMARY KEY,
                entry_date DATE NOT NULL,
                
                -- Basic info
                activity_type VARCHAR NOT NULL,
                name VARCHAR,
                description VARCHAR,
                start_time TIMESTAMP,
                
                -- Duration and distance
                duration_minutes FLOAT,
                distance_km FLOAT,
                elevation_gain_m FLOAT,
                elevation_loss_m FLOAT,
                
                -- Speed
                average_speed_kmh FLOAT,
                max_speed_kmh FLOAT,
                
                -- Heart rate
                average_heart_rate FLOAT,
                max_heart_rate FLOAT,
                heart_rate_zones_json VARCHAR,  -- JSON array of time in each zone
                
                -- Power (cycling)
                average_power_watts FLOAT,
                max_power_watts FLOAT,
                normalized_power_watts FLOAT,
                intensity_factor FLOAT,
                training_stress_score FLOAT,
                
                -- Cadence
                average_cadence FLOAT,
                max_cadence FLOAT,
                
                -- Perceived effort
                suffer_score FLOAT,
                perceived_exertion INTEGER,  -- 1-10 RPE scale
                
                -- Calories
                calories_burned FLOAT,
                
                -- Weather during activity
                temperature_c FLOAT,
                humidity_percent INTEGER,
                wind_speed_kmh FLOAT,
                
                -- Source tracking
                source VARCHAR DEFAULT 'strava',
                external_id VARCHAR,  -- Strava activity ID
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # ===== MEALS TABLE =====
        # Food intake with nutritional breakdown
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS meals (
                id VARCHAR PRIMARY KEY,
                entry_date DATE NOT NULL,
                
                -- Meal info
                meal_type VARCHAR NOT NULL,  -- breakfast, lunch, dinner, snack, drink
                time_consumed TIME,
                description VARCHAR NOT NULL,
                
                -- Nutritional estimates (can be LLM-generated or manual)
                calories FLOAT,
                protein_g FLOAT,
                carbs_g FLOAT,
                fat_g FLOAT,
                fiber_g FLOAT,
                sugar_g FLOAT,
                sodium_mg FLOAT,
                
                -- Micronutrients (optional)
                vitamin_a_iu FLOAT,
                vitamin_c_mg FLOAT,
                vitamin_d_iu FLOAT,
                calcium_mg FLOAT,
                iron_mg FLOAT,
                potassium_mg FLOAT,
                magnesium_mg FLOAT,
                
                -- Hydration
                water_ml FLOAT,
                
                -- Flags
                contains_alcohol BOOLEAN DEFAULT FALSE,
                alcohol_units FLOAT,
                alcohol_type VARCHAR,
                
                contains_caffeine BOOLEAN DEFAULT FALSE,
                caffeine_mg FLOAT,
                
                -- Trigger tracking (for headaches, etc.)
                trigger_foods VARCHAR[],  -- e.g., ['aged cheese', 'red wine']
                is_trigger_suspected BOOLEAN DEFAULT FALSE,
                
                -- Estimation metadata
                nutrition_source VARCHAR DEFAULT 'estimated',  -- 'estimated', 'manual', 'scanned', 'api'
                estimation_confidence FLOAT,  -- 0-1 confidence in nutritional estimates
                llm_reasoning VARCHAR,  -- LLM's explanation of estimation
                
                -- Notes
                notes VARCHAR,
                
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # ===== SYMPTOMS TABLE =====
        # Health symptoms with detailed tracking
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS symptoms (
                id VARCHAR PRIMARY KEY,
                entry_date DATE NOT NULL,
                
                -- Symptom identification
                symptom_type VARCHAR NOT NULL,
                symptom_subtype VARCHAR,  -- e.g., 'migraine', 'tension', 'cluster' for headaches
                custom_type VARCHAR,
                
                -- Severity and timing
                severity INTEGER NOT NULL,  -- 1-10
                onset_time TIME,
                end_time TIME,
                duration_minutes INTEGER,
                
                -- Location (for pain-based symptoms)
                body_location VARCHAR,
                custom_location VARCHAR,
                laterality VARCHAR,  -- 'left', 'right', 'bilateral', 'central'
                
                -- Character (for pain)
                pain_character VARCHAR,  -- 'throbbing', 'stabbing', 'dull', 'burning', etc.
                
                -- Associated symptoms
                with_nausea BOOLEAN DEFAULT FALSE,
                with_light_sensitivity BOOLEAN DEFAULT FALSE,
                with_sound_sensitivity BOOLEAN DEFAULT FALSE,
                with_aura BOOLEAN DEFAULT FALSE,
                with_visual_disturbance BOOLEAN DEFAULT FALSE,
                
                -- Triggers identified
                suspected_triggers VARCHAR[],
                
                -- Treatment
                treatment_taken VARCHAR,
                treatment_effective BOOLEAN,
                
                -- Notes
                notes VARCHAR,
                
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # ===== WEATHER TABLE =====
        # Environmental conditions
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS weather (
                id VARCHAR PRIMARY KEY,
                entry_date DATE NOT NULL,
                recorded_at TIMESTAMP,
                
                -- Temperature
                temp_c FLOAT,
                temp_high_c FLOAT,
                temp_low_c FLOAT,
                feels_like_c FLOAT,
                
                -- Atmospheric
                pressure_hpa FLOAT,
                pressure_trend VARCHAR,  -- 'rising', 'falling', 'stable'
                pressure_change FLOAT,  -- change from previous day
                humidity_percent INTEGER,
                
                -- Wind
                wind_speed_kmh FLOAT,
                wind_gust_kmh FLOAT,
                wind_direction_deg INTEGER,
                
                -- Precipitation
                precipitation_mm FLOAT,
                precipitation_probability INTEGER,
                
                -- Conditions
                description VARCHAR,
                cloud_cover_percent INTEGER,
                visibility_km FLOAT,
                uv_index FLOAT,
                
                -- Air quality
                aqi INTEGER,  -- Air Quality Index
                pm25 FLOAT,
                pm10 FLOAT,
                
                -- Astronomy (for seasonal affective analysis)
                sunrise TIME,
                sunset TIME,
                daylight_minutes INTEGER,
                moon_phase VARCHAR,
                
                -- Source
                source VARCHAR DEFAULT 'openweathermap',
                location_lat FLOAT,
                location_lon FLOAT,
                
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                UNIQUE(entry_date, source)
            )
        """)
        
        # ===== VITALS TABLE =====
        # Manual health measurements
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS vitals (
                id VARCHAR PRIMARY KEY,
                entry_date DATE NOT NULL,
                recorded_at TIME,
                
                -- Weight
                weight_kg FLOAT,
                body_fat_percent FLOAT,
                muscle_mass_kg FLOAT,
                
                -- Blood pressure
                systolic_bp INTEGER,
                diastolic_bp INTEGER,
                
                -- Heart
                resting_heart_rate INTEGER,
                
                -- Blood glucose
                blood_glucose_mgdl FLOAT,
                glucose_timing VARCHAR,  -- 'fasting', 'post_meal', 'random'
                
                -- Temperature
                body_temperature_c FLOAT,
                
                -- Respiratory
                blood_oxygen_percent INTEGER,
                respiratory_rate INTEGER,
                
                -- Other
                notes VARCHAR,
                source VARCHAR DEFAULT 'manual',
                
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # ===== MEDICATIONS TABLE =====
        # Medication tracking
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS medications (
                id VARCHAR PRIMARY KEY,
                entry_date DATE NOT NULL,
                time_taken TIME,
                
                -- Medication info
                name VARCHAR NOT NULL,
                dosage VARCHAR,
                dosage_mg FLOAT,
                form VARCHAR,  -- 'tablet', 'capsule', 'liquid', 'injection', etc.
                
                -- Purpose
                purpose VARCHAR,  -- 'pain', 'preventive', 'rescue', etc.
                for_symptom_id VARCHAR,  -- links to symptoms table
                
                -- Effectiveness (tracked later)
                effectiveness INTEGER,  -- 1-10
                side_effects VARCHAR,
                
                -- Prescription info
                is_prescription BOOLEAN DEFAULT FALSE,
                prescribing_doctor VARCHAR,
                
                notes VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # ===== SUPPLEMENTS TABLE =====
        # Supplement intake tracking
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS supplements (
                id VARCHAR PRIMARY KEY,
                entry_date DATE NOT NULL,
                time_taken TIME,
                
                -- Supplement info
                name VARCHAR NOT NULL,
                brand VARCHAR,
                dosage VARCHAR,
                dosage_amount FLOAT,
                dosage_unit VARCHAR,  -- 'mg', 'mcg', 'IU', 'g'
                
                -- Type
                supplement_type VARCHAR,  -- 'vitamin', 'mineral', 'herb', 'amino_acid', etc.
                
                notes VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # ===== HYDRATION TABLE =====
        # Fluid intake tracking
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS hydration (
                id VARCHAR PRIMARY KEY,
                entry_date DATE NOT NULL,
                time_consumed TIME,
                
                -- Beverage info
                beverage_type VARCHAR NOT NULL,  -- 'water', 'coffee', 'tea', 'juice', etc.
                volume_ml FLOAT NOT NULL,
                
                -- Content
                contains_caffeine BOOLEAN DEFAULT FALSE,
                caffeine_mg FLOAT,
                contains_alcohol BOOLEAN DEFAULT FALSE,
                alcohol_units FLOAT,
                contains_sugar BOOLEAN DEFAULT FALSE,
                sugar_g FLOAT,
                
                -- Electrolytes
                sodium_mg FLOAT,
                potassium_mg FLOAT,
                
                notes VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # ===== INCIDENTS TABLE =====
        # Notable health events
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id VARCHAR PRIMARY KEY,
                entry_date DATE NOT NULL,
                time_occurred TIME,
                
                -- Incident info
                incident_type VARCHAR NOT NULL,
                custom_type VARCHAR,
                severity INTEGER,  -- 1-10
                
                -- Location
                location VARCHAR,
                custom_location VARCHAR,
                
                -- Details
                description VARCHAR,
                duration_minutes INTEGER,
                
                -- Triggers and causes
                suspected_cause VARCHAR,
                
                -- Actions taken
                action_taken VARCHAR,
                medical_attention BOOLEAN DEFAULT FALSE,
                
                notes VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # ===== DAILY SUMMARY TABLE =====
        # Aggregated daily metrics for quick analysis
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_summary (
                entry_date DATE PRIMARY KEY,
                
                -- Subjective wellbeing
                overall_wellbeing INTEGER,
                energy_level INTEGER,
                stress_level INTEGER,
                mood VARCHAR,
                mood_score INTEGER,  -- 1-10 numeric mood
                
                -- Sleep summary (from sleep table)
                sleep_score INTEGER,
                total_sleep_minutes INTEGER,
                sleep_efficiency INTEGER,
                hrv_average FLOAT,
                
                -- Activity summary (from activities table)
                activity_count INTEGER DEFAULT 0,
                total_activity_minutes FLOAT DEFAULT 0,
                total_distance_km FLOAT DEFAULT 0,
                total_elevation_m FLOAT DEFAULT 0,
                total_calories_burned FLOAT DEFAULT 0,
                
                -- Nutrition summary (from meals table)
                meal_count INTEGER DEFAULT 0,
                total_calories FLOAT DEFAULT 0,
                total_protein_g FLOAT DEFAULT 0,
                total_carbs_g FLOAT DEFAULT 0,
                total_fat_g FLOAT DEFAULT 0,
                total_fiber_g FLOAT DEFAULT 0,
                total_water_ml FLOAT DEFAULT 0,
                total_caffeine_mg FLOAT DEFAULT 0,
                total_alcohol_units FLOAT DEFAULT 0,
                
                -- Symptom summary
                symptom_count INTEGER DEFAULT 0,
                worst_symptom_severity INTEGER,
                has_headache BOOLEAN DEFAULT FALSE,
                has_neuralgiaform BOOLEAN DEFAULT FALSE,
                
                -- Incident summary
                incident_count INTEGER DEFAULT 0,
                
                -- Weather summary (from weather table)
                temp_avg_c FLOAT,
                pressure_hpa FLOAT,
                pressure_change FLOAT,
                humidity_percent INTEGER,
                
                -- Vitals summary
                weight_kg FLOAT,
                resting_hr INTEGER,
                
                -- Medication summary
                medication_count INTEGER DEFAULT 0,
                rescue_medication_used BOOLEAN DEFAULT FALSE,
                
                -- Supplement summary
                supplement_count INTEGER DEFAULT 0,
                
                -- Notes
                morning_notes VARCHAR,
                evening_notes VARCHAR,
                general_notes VARCHAR,
                
                -- Metadata
                is_complete BOOLEAN DEFAULT FALSE,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # ===== DAILY FACTORS TABLE =====
        # Boolean/checkbox factors from quick_log (cat, sleep disruptions, etc.)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_factors (
                entry_date DATE PRIMARY KEY,
                
                -- Sleep disruption factors
                cat_in_room BOOLEAN DEFAULT FALSE,
                cat_woke_me BOOLEAN DEFAULT FALSE,
                
                -- Add more boolean factors as needed
                -- poor_sleep_quality BOOLEAN DEFAULT FALSE,
                -- late_night_screen BOOLEAN DEFAULT FALSE,
                
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # ===== CORRELATION CACHE TABLE =====
        # Pre-computed correlations for faster analysis
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS correlation_cache (
                id VARCHAR PRIMARY KEY,
                computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                days_analyzed INTEGER,
                start_date DATE,
                end_date DATE,
                
                -- Correlation pairs
                factor_a VARCHAR,
                factor_b VARCHAR,
                correlation FLOAT,
                p_value FLOAT,
                sample_size INTEGER,
                
                -- Metadata
                is_significant BOOLEAN
            )
        """)
        
        # ===== CONSULTATIONS TABLE =====
        # AI Health Advisor visit records
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS consultations (
                id VARCHAR PRIMARY KEY,
                consultation_date DATE NOT NULL,
                started_at TIMESTAMP NOT NULL,
                ended_at TIMESTAMP,
                
                -- Data range reviewed
                data_start_date DATE,
                data_end_date DATE,
                days_reviewed INTEGER,
                
                -- Chief complaint / reason for visit
                chief_complaint VARCHAR,
                
                -- AI-generated summary
                summary VARCHAR,
                
                -- Key findings from the consultation
                key_findings VARCHAR,
                
                -- Patterns identified
                patterns_identified VARCHAR,
                
                -- Recommendations given
                recommendations VARCHAR,
                
                -- Potential triggers discussed
                triggers_discussed VARCHAR,
                
                -- Follow-up actions
                follow_up_actions VARCHAR,
                
                -- Conversation stats
                message_count INTEGER DEFAULT 0,
                
                -- AI provider used
                provider VARCHAR,
                
                -- Full conversation (JSON)
                conversation_json VARCHAR,
                
                -- User notes about the consultation
                user_notes VARCHAR,
                
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes for common queries
        self._create_indexes()
    
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
                pass  # Index may already exist
        
        # Auto-migrate: add pressure_change column if missing (renamed from pressure_change_3h)
        try:
            self.conn.execute("SELECT pressure_change FROM weather LIMIT 1")
        except Exception:
            try:
                self.conn.execute("ALTER TABLE weather ADD COLUMN pressure_change FLOAT")
            except Exception:
                pass  # Column may already exist under different scenario
    
    def upsert_entry(self, entry: DiaryEntry) -> None:
        """Insert or update a diary entry across all relevant tables."""
        import uuid
        from ..models.health import SymptomType
        
        entry_date = entry.entry_date
        
        # ===== SLEEP =====
        if entry.integrations.sleep:
            s = entry.integrations.sleep
            sleep_id = f"sleep_{entry_date.isoformat()}_oura"
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
                sleep_id, entry_date, s.bedtime, s.wake_time,
                s.total_sleep_minutes, s.rem_sleep_minutes, s.deep_sleep_minutes,
                s.light_sleep_minutes, s.awake_minutes,
                s.sleep_score, s.efficiency_percent,
                s.lowest_heart_rate, s.average_heart_rate, s.hrv_average,
                s.respiratory_rate, s.readiness_score, s.restless_periods, 'oura'
            ])
        
        # ===== ACTIVITIES =====
        self.conn.execute("DELETE FROM activities WHERE entry_date = ?", [entry_date])
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
                activity.description, activity.start_time,
                activity.duration_minutes, activity.distance_km, activity.elevation_gain_m,
                activity.average_speed_kmh, activity.max_speed_kmh,
                activity.average_heart_rate, activity.max_heart_rate,
                activity.average_power_watts, activity.normalized_power_watts,
                activity.average_cadence, activity.suffer_score, 'strava', activity.activity_id
            ])
        
        # ===== WEATHER =====
        if entry.integrations.weather:
            w = entry.integrations.weather
            weather_id = f"weather_{entry_date.isoformat()}"
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
        # Meals are now managed separately via add_meal_with_nutrition
        # Don't delete or re-insert them here to avoid conflicts
        
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
                symptom.severity.value, symptom.onset_time, symptom.duration_minutes,
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
                incident.custom_location, incident.description, incident.time_occurred
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
                med.time_taken, med.reason, med.notes
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
                supp.time_taken, supp.notes
            ])
        
        # ===== DAILY SUMMARY =====
        self._update_daily_summary(entry)
    
    def _update_daily_summary(self, entry: DiaryEntry) -> None:
        """Update the daily summary table with aggregated data."""
        from ..models.health import SymptomType
        
        entry_date = entry.entry_date
        
        # Calculate aggregates
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
            len(entry.symptoms), worst_severity, has_headache, has_neuralgiaform,
            len(entry.incidents),
            w.temp_avg_c if w else None, w.pressure_hpa if w else None,
            w.humidity_percent if w else None,
            entry.morning_notes, entry.evening_notes, entry.general_notes,
            entry.is_complete, datetime.now()
        ])
        
        # Ensure data is persisted
        self.conn.execute("CHECKPOINT")
    
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
            meal_id, entry_date, meal_type, time_consumed, description,
            nutrition.get('calories'), nutrition.get('protein_g'), nutrition.get('carbs_g'),
            nutrition.get('fat_g'), nutrition.get('fiber_g'), nutrition.get('sugar_g'),
            nutrition.get('sodium_mg'), nutrition.get('water_ml'),
            nutrition.get('caffeine_mg'), nutrition.get('caffeine_mg', 0) > 0,
            nutrition.get('alcohol_units', 0) > 0, nutrition.get('alcohol_units'),
            nutrition.get('source', 'estimated'), nutrition.get('confidence'),
            nutrition.get('reasoning'), notes
        ])
        
        # Ensure data is persisted
        self.conn.execute("CHECKPOINT")
        
        return meal_id
    
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
            params.append(start_date)
        if end_date:
            conditions.append("entry_date <= ?")
            params.append(end_date)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY entry_date"
        
        return self.conn.execute(query, params).df()
    
    def sync_quick_log(self, entry_date: date, quick_log: dict, totals: dict) -> None:
        """
        Sync quick_log data to DuckDB.
        
        Updates:
        - daily_factors: boolean checkbox items (cat_in_room, cat_woke_me, etc.)
        - daily_summary: caffeine and alcohol totals
        """
        # Update daily_factors with checkbox values
        cat_in_room = quick_log.get('cat_in_room', 0) == 1
        cat_woke_me = quick_log.get('cat_woke_me', 0) == 1
        
        self.conn.execute("""
            INSERT OR REPLACE INTO daily_factors (
                entry_date, cat_in_room, cat_woke_me, updated_at
            ) VALUES (?, ?, ?, ?)
        """, [entry_date, cat_in_room, cat_woke_me, datetime.now()])
        
        # Update daily_summary with caffeine/alcohol totals
        caffeine_mg = totals.get('total_caffeine_mg', 0)
        alcohol_units = totals.get('total_alcohol_units', 0)
        
        # First ensure the row exists
        self.conn.execute("""
            INSERT INTO daily_summary (entry_date, total_caffeine_mg, total_alcohol_units, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (entry_date) DO UPDATE SET
                total_caffeine_mg = excluded.total_caffeine_mg,
                total_alcohol_units = excluded.total_alcohol_units,
                updated_at = excluded.updated_at
        """, [entry_date, caffeine_mg, alcohol_units, datetime.now()])
        
        self.conn.execute("CHECKPOINT")
    
    def get_analysis_data(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """
        Get comprehensive daily data for correlation analysis.
        
        Joins daily_summary, daily_factors, and aggregated data.
        """
        query = """
            SELECT 
                ds.*,
                df.cat_in_room,
                df.cat_woke_me,
                -- Nutrition from meals table
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
            params.append(start_date)
        if end_date:
            conditions.append("ds.entry_date <= ?")
            params.append(end_date)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY ds.entry_date"
        
        return self.conn.execute(query, params).df()
    
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
            params.append(start_date)
        if end_date:
            conditions.append("entry_date <= ?")
            params.append(end_date)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " GROUP BY entry_date ORDER BY entry_date"
        
        return self.conn.execute(query, params).df()
    
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
            params.append(start_date)
        if end_date:
            conditions.append("entry_date <= ?")
            params.append(end_date)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY entry_date"
        
        return self.conn.execute(query, params).df()
    
    def query(self, sql: str, params: list = None) -> pd.DataFrame:
        """Execute arbitrary SQL query and return DataFrame."""
        return self.conn.execute(sql, params or []).df()
    
    def get_table_info(self) -> pd.DataFrame:
        """Get information about all tables."""
        return self.query("""
            SELECT table_name, column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'main'
            ORDER BY table_name, ordinal_position
        """)
    
    def get_schema_summary(self) -> str:
        """Get a human-readable summary of all tables and columns."""
        tables = self.query("""
            SELECT DISTINCT table_name 
            FROM information_schema.columns 
            WHERE table_schema = 'main'
            ORDER BY table_name
        """)
        
        result = []
        for table_name in tables['table_name']:
            cols = self.query(f"""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'main' AND table_name = '{table_name}'
                ORDER BY ordinal_position
            """)
            
            result.append(f"\n=== {table_name.upper()} ===")
            for _, row in cols.iterrows():
                result.append(f"  {row['column_name']}: {row['data_type']}")
        
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
            consultation_id, consultation_date, started_at, ended_at,
            data_start, data_end, days_reviewed,
            chief_complaint, summary, key_findings, patterns_identified,
            recommendations, triggers_discussed, follow_up_actions,
            message_count, provider, conversation_json
        ])
    
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
            params.append(start_date)
        if end_date:
            conditions.append("consultation_date <= ?")
            params.append(end_date)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        
        return self.conn.execute(query, params).df()
    
    def close(self) -> None:
        """Close database connection with checkpoint."""
        if self._conn:
            # Checkpoint to flush WAL and reclaim space
            try:
                self._conn.execute("CHECKPOINT")
            except Exception:
                pass
            self._conn.close()
            self._conn = None
    
    def __enter__(self) -> "AnalyticsDB":
        return self
    
    def __exit__(self, *args) -> None:
        self.close()
