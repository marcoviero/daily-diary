"""Models for external data integrations."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class WeatherData(BaseModel):
    """Weather conditions for a day."""
    
    # Temperature
    temp_high_f: Optional[float] = None
    temp_low_f: Optional[float] = None
    temp_avg_f: Optional[float] = None
    
    # Pressure (important for headaches!)
    pressure_hpa: Optional[float] = None
    pressure_change_hpa: Optional[float] = None  # Change from previous day
    
    # Humidity
    humidity_percent: Optional[int] = None
    
    # Conditions
    description: Optional[str] = None  # e.g., "partly cloudy"
    precipitation_mm: Optional[float] = None
    wind_speed_mph: Optional[float] = None
    
    # UV index
    uv_index: Optional[int] = None
    
    # Source metadata
    location: Optional[str] = None
    fetched_at: Optional[datetime] = None


class ActivityData(BaseModel):
    """Exercise/activity data from Strava."""
    
    activity_id: Optional[str] = None
    activity_type: str  # e.g., "Ride", "Run", "Walk"
    name: Optional[str] = None
    
    # Duration and distance
    duration_minutes: float
    distance_km: Optional[float] = None
    
    # Effort metrics
    elevation_gain_m: Optional[float] = None
    average_speed_kmh: Optional[float] = None
    max_speed_kmh: Optional[float] = None
    average_heart_rate: Optional[float] = None
    max_heart_rate: Optional[float] = None
    average_power_watts: Optional[float] = None
    normalized_power_watts: Optional[float] = None

    # Cycling-specific
    average_cadence: Optional[float] = None

    # Perceived effort
    suffer_score: Optional[float] = None
    
    # Timing
    start_time: Optional[datetime] = None
    
    # Notes
    description: Optional[str] = None


class SleepData(BaseModel):
    """Sleep data from Oura Ring."""
    
    # Timing
    bedtime: Optional[datetime] = None
    wake_time: Optional[datetime] = None
    
    # Duration (minutes)
    total_sleep_minutes: Optional[int] = None
    rem_sleep_minutes: Optional[int] = None
    deep_sleep_minutes: Optional[int] = None
    light_sleep_minutes: Optional[int] = None
    awake_minutes: Optional[int] = None
    
    # Quality scores (0-100)
    sleep_score: Optional[int] = None
    efficiency_percent: Optional[int] = None
    
    # Physiological
    lowest_heart_rate: Optional[float] = None
    average_heart_rate: Optional[float] = None
    hrv_average: Optional[float] = None
    respiratory_rate: Optional[float] = None
    
    # Readiness (Oura's overall readiness score)
    readiness_score: Optional[int] = None
    
    # Contributing factors
    restless_periods: Optional[int] = None


class DailyIntegrations(BaseModel):
    """Container for all integrated data for a day."""
    
    weather: Optional[WeatherData] = None
    activities: list[ActivityData] = Field(default_factory=list)
    sleep: Optional[SleepData] = None  # Previous night's sleep
    
    @property
    def total_activity_minutes(self) -> float:
        """Total exercise duration for the day."""
        return sum(a.duration_minutes for a in self.activities)
    
    @property
    def total_elevation_gain(self) -> float:
        """Total climbing for the day."""
        return sum(a.elevation_gain_m or 0 for a in self.activities)
