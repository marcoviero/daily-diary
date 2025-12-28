"""Weather API client using Open-Meteo (free, no API key required)."""

from datetime import date, datetime, timedelta
from typing import Optional

import httpx

from ..models.integrations import WeatherData
from ..utils.config import Settings, get_settings


class WeatherClient:
    """
    Client for fetching weather data from Open-Meteo.
    
    Open-Meteo provides free historical and forecast weather data
    with daily summaries - perfect for consistent day-to-day comparison.
    No API key required.
    """
    
    BASE_URL = "https://api.open-meteo.com/v1/forecast"
    
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._client: Optional[httpx.Client] = None
    
    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=30.0)
        return self._client
    
    @property
    def is_configured(self) -> bool:
        # Open-Meteo doesn't require API key, just lat/lon
        return True
    
    def get_weather_for_date(
        self,
        target_date: date,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
    ) -> Optional[WeatherData]:
        """
        Fetch daily weather summary for a specific date.
        
        Returns consistent daily metrics:
        - temp_high_c, temp_low_c, temp_avg_c (mean)
        - pressure at noon (consistent time for comparison)
        - humidity, precipitation, wind
        
        Also calculates pressure_change_hpa from previous day.
        """
        lat = lat or self.settings.default_latitude
        lon = lon or self.settings.default_longitude
        
        # Fetch 2 days to calculate pressure change
        start_date = target_date - timedelta(days=1)
        end_date = target_date
        
        try:
            response = self.client.get(
                self.BASE_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "daily": [
                        "temperature_2m_max",
                        "temperature_2m_min",
                        "temperature_2m_mean",
                        "precipitation_sum",
                        "precipitation_hours",
                        "wind_speed_10m_max",
                    ],
                    "hourly": ["surface_pressure", "relative_humidity_2m"],
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "timezone": "auto",
                },
            )
            response.raise_for_status()
            data = response.json()
            
            daily = data.get("daily", {})
            hourly = data.get("hourly", {})
            
            # Find index for target date in daily data
            dates = daily.get("time", [])
            try:
                day_idx = dates.index(target_date.isoformat())
            except ValueError:
                return None
            
            # Get noon pressure for consistent comparison (index 12 for noon hour)
            # Each day has 24 hours, so target day's noon is at index: day_idx * 24 + 12
            pressures = hourly.get("surface_pressure", [])
            humidities = hourly.get("relative_humidity_2m", [])
            
            noon_hour_idx = day_idx * 24 + 12
            prev_noon_idx = (day_idx - 1) * 24 + 12 if day_idx > 0 else None
            
            pressure_noon = pressures[noon_hour_idx] if noon_hour_idx < len(pressures) else None
            pressure_prev = pressures[prev_noon_idx] if prev_noon_idx and prev_noon_idx < len(pressures) else None
            
            # Calculate pressure change from previous day
            pressure_change = None
            if pressure_noon is not None and pressure_prev is not None:
                pressure_change = round(pressure_noon - pressure_prev, 1)
            
            # Average humidity for the day (noon +/- 6 hours)
            day_start_hour = day_idx * 24
            day_humidities = humidities[day_start_hour:day_start_hour + 24]
            avg_humidity = sum(day_humidities) / len(day_humidities) if day_humidities else None
            
            # Get precipitation description
            precip_mm = daily.get("precipitation_sum", [0])[day_idx] or 0
            precip_hours = daily.get("precipitation_hours", [0])[day_idx] or 0
            
            if precip_mm > 10:
                description = "Heavy rain"
            elif precip_mm > 2:
                description = "Rain"
            elif precip_mm > 0:
                description = "Light rain"
            elif precip_hours > 0:
                description = "Drizzle"
            else:
                description = "Dry"
            
            return WeatherData(
                temp_high_c=daily.get("temperature_2m_max", [None])[day_idx],
                temp_low_c=daily.get("temperature_2m_min", [None])[day_idx],
                temp_avg_c=daily.get("temperature_2m_mean", [None])[day_idx],
                pressure_hpa=pressure_noon,
                pressure_change_hpa=pressure_change,
                humidity_percent=round(avg_humidity) if avg_humidity else None,
                precipitation_mm=precip_mm,
                wind_speed_kmh=daily.get("wind_speed_10m_max", [None])[day_idx],
                description=description,
                location=f"{lat:.2f}, {lon:.2f}",
                fetched_at=datetime.now(),
            )
            
        except httpx.HTTPError as e:
            print(f"Weather API error: {e}")
            return None
        except (KeyError, IndexError, TypeError) as e:
            print(f"Weather data parsing error: {e}")
            return None
    
    def get_current_weather(
        self,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
    ) -> Optional[WeatherData]:
        """Fetch today's weather summary."""
        return self.get_weather_for_date(date.today(), lat, lon)
    
    def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None
    
    def __enter__(self) -> "WeatherClient":
        return self
    
    def __exit__(self, *args) -> None:
        self.close()
