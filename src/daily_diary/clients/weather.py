"""OpenWeatherMap API client."""

from datetime import date, datetime
from typing import Optional

import httpx

from ..models.integrations import WeatherData
from ..utils.config import Settings, get_settings


class WeatherClient:
    """Client for fetching weather data from OpenWeatherMap."""
    
    BASE_URL = "https://api.openweathermap.org/data/2.5"
    
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
        return self.settings.has_weather
    
    def get_current_weather(
        self,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
    ) -> Optional[WeatherData]:
        """Fetch current weather conditions."""
        if not self.is_configured:
            return None
        
        lat = lat or self.settings.default_latitude
        lon = lon or self.settings.default_longitude
        
        try:
            response = self.client.get(
                f"{self.BASE_URL}/weather",
                params={
                    "lat": lat,
                    "lon": lon,
                    "appid": self.settings.openweather_api_key,
                    "units": "imperial",  # Fahrenheit
                },
            )
            response.raise_for_status()
            data = response.json()
            
            return WeatherData(
                temp_avg_f=data["main"]["temp"],
                temp_high_f=data["main"]["temp_max"],
                temp_low_f=data["main"]["temp_min"],
                pressure_hpa=data["main"]["pressure"],
                humidity_percent=data["main"]["humidity"],
                description=data["weather"][0]["description"] if data.get("weather") else None,
                wind_speed_mph=data["wind"]["speed"] if data.get("wind") else None,
                location=data.get("name"),
                fetched_at=datetime.now(),
            )
        except httpx.HTTPError as e:
            print(f"Weather API error: {e}")
            return None
    
    def get_weather_for_date(
        self,
        target_date: date,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
    ) -> Optional[WeatherData]:
        """
        Fetch weather for a specific date.
        
        Note: For historical data, you'd need OpenWeatherMap's One Call API 3.0
        with a subscription. This implementation returns current weather
        if the date is today, otherwise returns None.
        """
        if target_date == date.today():
            return self.get_current_weather(lat, lon)
        
        # Historical data requires paid API - return None for past dates
        # Could be extended to use One Call API 3.0 with subscription
        return None
    
    def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None
    
    def __enter__(self) -> "WeatherClient":
        return self
    
    def __exit__(self, *args) -> None:
        self.close()
