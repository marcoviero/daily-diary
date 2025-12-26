"""DuckDB analytics database for health diary data."""

from datetime import date, datetime
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd

from ..models.entry import DiaryEntry
from ..models.integrations import ActivityData, SleepData, WeatherData
from ..utils.config import get_settings


class AnalyticsDB:
    """
    DuckDB database for storing and analyzing health diary data.
    
    Stores denormalized time series data optimized for analytical queries:
    - Daily summaries (weather, sleep, activity totals, symptom counts)
    - Individual activities
    - Individual symptoms
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
        """Initialize database schema."""
        # Daily summary table - one row per day
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_summary (
                entry_date DATE PRIMARY KEY,
                
                -- Wellbeing
                overall_wellbeing INTEGER,
                energy_level INTEGER,
                stress_level INTEGER,
                mood VARCHAR,
                
                -- Symptom aggregates
                symptom_count INTEGER DEFAULT 0,
                worst_symptom_severity INTEGER,
                has_headache BOOLEAN DEFAULT FALSE,
                has_neuralgiaform BOOLEAN DEFAULT FALSE,
                
                -- Incident aggregates
                incident_count INTEGER DEFAULT 0,
                
                -- Meal aggregates
                meal_count INTEGER DEFAULT 0,
                alcohol_units FLOAT DEFAULT 0,
                has_caffeine BOOLEAN DEFAULT FALSE,
                
                -- Weather
                temp_avg_c FLOAT,
                temp_high_c FLOAT,
                temp_low_c FLOAT,
                pressure_hpa FLOAT,
                humidity_percent INTEGER,
                wind_speed_kmh FLOAT,
                weather_description VARCHAR,
                
                -- Sleep (previous night)
                sleep_score INTEGER,
                total_sleep_minutes INTEGER,
                deep_sleep_minutes INTEGER,
                rem_sleep_minutes INTEGER,
                light_sleep_minutes INTEGER,
                sleep_efficiency INTEGER,
                hrv_average FLOAT,
                lowest_heart_rate FLOAT,
                avg_heart_rate_sleep FLOAT,
                respiratory_rate FLOAT,
                bedtime TIMESTAMP,
                wake_time TIMESTAMP,
                
                -- Activity totals
                activity_count INTEGER DEFAULT 0,
                total_activity_minutes FLOAT DEFAULT 0,
                total_distance_km FLOAT DEFAULT 0,
                total_elevation_m FLOAT DEFAULT 0,
                avg_heart_rate_activity FLOAT,
                max_heart_rate_activity FLOAT,
                avg_power_watts FLOAT,
                total_suffer_score FLOAT,
                
                -- Metadata
                is_complete BOOLEAN DEFAULT FALSE,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Individual activities table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS activities (
                id VARCHAR PRIMARY KEY,
                entry_date DATE,
                activity_type VARCHAR,
                name VARCHAR,
                start_time TIMESTAMP,
                duration_minutes FLOAT,
                distance_km FLOAT,
                elevation_gain_m FLOAT,
                average_speed_kmh FLOAT,
                max_speed_kmh FLOAT,
                average_heart_rate FLOAT,
                max_heart_rate FLOAT,
                average_power_watts FLOAT,
                normalized_power_watts FLOAT,
                average_cadence FLOAT,
                suffer_score FLOAT,
                description VARCHAR
            )
        """)
        
        # Individual symptoms table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS symptoms (
                id VARCHAR PRIMARY KEY,
                entry_date DATE,
                symptom_type VARCHAR,
                custom_type VARCHAR,
                severity INTEGER,
                location VARCHAR,
                custom_location VARCHAR,
                onset_time TIME,
                duration_minutes INTEGER,
                notes VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Individual incidents table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id VARCHAR PRIMARY KEY,
                entry_date DATE,
                incident_type VARCHAR,
                custom_type VARCHAR,
                location VARCHAR,
                custom_location VARCHAR,
                severity INTEGER,
                description VARCHAR,
                time_occurred TIME,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Meals table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS meals (
                id VARCHAR PRIMARY KEY,
                entry_date DATE,
                meal_type VARCHAR,
                description VARCHAR,
                time_consumed TIME,
                contains_alcohol BOOLEAN DEFAULT FALSE,
                alcohol_units FLOAT,
                contains_caffeine BOOLEAN DEFAULT FALSE,
                trigger_foods VARCHAR[],
                notes VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    
    def upsert_entry(self, entry: DiaryEntry) -> None:
        """Insert or update a diary entry in the analytics database."""
        from ..models.health import SymptomType
        import uuid
        
        # Calculate aggregates
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
        has_caffeine = any(m.contains_caffeine for m in entry.meals)
        
        # Activity aggregates
        activities = entry.integrations.activities or []
        total_activity_mins = sum(a.duration_minutes for a in activities)
        total_distance = sum(a.distance_km or 0 for a in activities)
        total_elevation = sum(a.elevation_gain_m or 0 for a in activities)
        
        hr_values = [a.average_heart_rate for a in activities if a.average_heart_rate]
        avg_hr = sum(hr_values) / len(hr_values) if hr_values else None
        max_hr = max((a.max_heart_rate or 0 for a in activities), default=None)
        
        power_values = [a.average_power_watts for a in activities if a.average_power_watts]
        avg_power = sum(power_values) / len(power_values) if power_values else None
        
        total_suffer = sum(a.suffer_score or 0 for a in activities)
        
        # Weather data
        w = entry.integrations.weather
        
        # Sleep data
        s = entry.integrations.sleep
        
        # Upsert daily summary
        self.conn.execute("""
            INSERT OR REPLACE INTO daily_summary VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?,
                ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?
            )
        """, [
            entry.entry_date,
            entry.overall_wellbeing, entry.energy_level, entry.stress_level, entry.mood,
            len(entry.symptoms), worst_severity, has_headache, has_neuralgiaform,
            len(entry.incidents),
            len(entry.meals), total_alcohol, has_caffeine,
            w.temp_avg_c if w else None, w.temp_high_c if w else None, w.temp_low_c if w else None,
            w.pressure_hpa if w else None, w.humidity_percent if w else None,
            w.wind_speed_kmh if w else None, w.description if w else None,
            s.sleep_score if s else None, s.total_sleep_minutes if s else None,
            s.deep_sleep_minutes if s else None, s.rem_sleep_minutes if s else None,
            s.light_sleep_minutes if s else None, s.efficiency_percent if s else None,
            s.hrv_average if s else None, s.lowest_heart_rate if s else None,
            s.average_heart_rate if s else None, s.respiratory_rate if s else None,
            s.bedtime if s else None, s.wake_time if s else None,
            len(activities), total_activity_mins, total_distance, total_elevation,
            avg_hr, max_hr, avg_power, total_suffer,
            entry.is_complete, datetime.now()
        ])
        
        # Upsert activities
        self.conn.execute("DELETE FROM activities WHERE entry_date = ?", [entry.entry_date])
        for activity in activities:
            activity_id = activity.activity_id or str(uuid.uuid4())
            self.conn.execute("""
                INSERT INTO activities VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                activity_id, entry.entry_date, activity.activity_type, activity.name,
                activity.start_time, activity.duration_minutes, activity.distance_km,
                activity.elevation_gain_m, activity.average_speed_kmh, activity.max_speed_kmh,
                activity.average_heart_rate, activity.max_heart_rate,
                activity.average_power_watts, activity.normalized_power_watts,
                activity.average_cadence, activity.suffer_score, activity.description
            ])
        
        # Upsert symptoms
        self.conn.execute("DELETE FROM symptoms WHERE entry_date = ?", [entry.entry_date])
        for symptom in entry.symptoms:
            symptom_id = str(uuid.uuid4())
            self.conn.execute("""
                INSERT INTO symptoms VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                symptom_id, entry.entry_date, symptom.type.value, symptom.custom_type,
                symptom.severity.value, symptom.location.value if symptom.location else None,
                symptom.custom_location, symptom.onset_time, symptom.duration_minutes,
                symptom.notes, datetime.now()
            ])
        
        # Upsert incidents
        self.conn.execute("DELETE FROM incidents WHERE entry_date = ?", [entry.entry_date])
        for incident in entry.incidents:
            incident_id = str(uuid.uuid4())
            self.conn.execute("""
                INSERT INTO incidents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                incident_id, entry.entry_date, incident.type.value, incident.custom_type,
                incident.location.value if incident.location else None, incident.custom_location,
                incident.severity.value, incident.description, incident.time_occurred, datetime.now()
            ])
        
        # Upsert meals
        self.conn.execute("DELETE FROM meals WHERE entry_date = ?", [entry.entry_date])
        for meal in entry.meals:
            meal_id = str(uuid.uuid4())
            self.conn.execute("""
                INSERT INTO meals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                meal_id, entry.entry_date, meal.meal_type.value, meal.description,
                meal.time_consumed, meal.contains_alcohol, meal.alcohol_units,
                meal.contains_caffeine, meal.trigger_foods, meal.notes, datetime.now()
            ])
    
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
    
    def get_correlation_matrix(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """Get correlation matrix between all numeric columns."""
        df = self.get_daily_summary_df(start_date, end_date)
        
        # Select numeric columns
        numeric_cols = df.select_dtypes(include=['number']).columns
        
        return df[numeric_cols].corr()
    
    def query(self, sql: str, params: list = None) -> pd.DataFrame:
        """Execute arbitrary SQL query and return DataFrame."""
        return self.conn.execute(sql, params or []).df()
    
    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
    
    def __enter__(self) -> "AnalyticsDB":
        return self
    
    def __exit__(self, *args) -> None:
        self.close()
