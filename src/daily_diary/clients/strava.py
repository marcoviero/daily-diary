"""Strava API client."""

from datetime import date, datetime, timedelta, timezone
from typing import Optional

import httpx

from ..models.integrations import ActivityData
from ..utils.config import Settings, get_settings


class StravaClient:
    """Client for fetching activity data from Strava."""
    
    AUTH_URL = "https://www.strava.com/oauth/token"
    API_URL = "https://www.strava.com/api/v3"
    
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._client: Optional[httpx.Client] = None
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
    
    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=30.0)
        return self._client
    
    @property
    def is_configured(self) -> bool:
        return self.settings.has_strava
    
    def _refresh_access_token(self) -> bool:
        """Refresh the access token using the refresh token."""
        if not self.is_configured:
            return False
        
        try:
            response = self.client.post(
                self.AUTH_URL,
                data={
                    "client_id": self.settings.strava_client_id,
                    "client_secret": self.settings.strava_client_secret,
                    "refresh_token": self.settings.strava_refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            response.raise_for_status()
            data = response.json()
            
            self._access_token = data["access_token"]
            self._token_expires_at = datetime.fromtimestamp(
                data["expires_at"], tz=timezone.utc
            )
            return True
        except httpx.HTTPError as e:
            print(f"Strava auth error: {e}")
            return False
    
    def _ensure_valid_token(self) -> bool:
        """Ensure we have a valid access token."""
        if self._access_token and self._token_expires_at:
            # Refresh if expiring in less than 5 minutes
            if datetime.now(timezone.utc) < self._token_expires_at - timedelta(minutes=5):
                return True
        return self._refresh_access_token()
    
    def _get_headers(self) -> dict[str, str]:
        """Get authorization headers."""
        return {"Authorization": f"Bearer {self._access_token}"}
    
    def get_activities_for_date(self, target_date: date) -> list[ActivityData]:
        """Fetch all activities for a specific date."""
        if not self.is_configured or not self._ensure_valid_token():
            return []
        
        # Calculate epoch timestamps for the day
        start_of_day = datetime.combine(target_date, datetime.min.time())
        end_of_day = datetime.combine(target_date, datetime.max.time())
        
        try:
            response = self.client.get(
                f"{self.API_URL}/athlete/activities",
                headers=self._get_headers(),
                params={
                    "after": int(start_of_day.timestamp()),
                    "before": int(end_of_day.timestamp()),
                    "per_page": 50,
                },
            )
            response.raise_for_status()
            activities_data = response.json()
            
            return [self._parse_activity(a) for a in activities_data]
        except httpx.HTTPError as e:
            print(f"Strava API error: {e}")
            return []
    
    def get_recent_activities(self, days: int = 7) -> list[ActivityData]:
        """Fetch activities from the last N days."""
        if not self.is_configured or not self._ensure_valid_token():
            return []
        
        after_date = datetime.now() - timedelta(days=days)
        
        try:
            response = self.client.get(
                f"{self.API_URL}/athlete/activities",
                headers=self._get_headers(),
                params={
                    "after": int(after_date.timestamp()),
                    "per_page": 100,
                },
            )
            response.raise_for_status()
            activities_data = response.json()
            
            return [self._parse_activity(a) for a in activities_data]
        except httpx.HTTPError as e:
            print(f"Strava API error: {e}")
            return []
    
    def _parse_activity(self, data: dict) -> ActivityData:
        """Parse Strava API response into ActivityData model."""
        return ActivityData(
            activity_id=str(data.get("id")),
            activity_type=data.get("type", "Unknown"),
            name=data.get("name"),
            duration_minutes=data.get("moving_time", 0) / 60,
            distance_km=data.get("distance", 0) / 1000 if data.get("distance") else None,
            elevation_gain_m=data.get("total_elevation_gain"),
            average_speed_kmh=(data.get("average_speed", 0) * 3.6) if data.get("average_speed") else None,
            max_speed_kmh=(data.get("max_speed", 0) * 3.6) if data.get("max_speed") else None,
            average_heart_rate=data.get("average_heartrate"),
            max_heart_rate=data.get("max_heartrate"),
            average_power_watts=data.get("average_watts"),
            average_cadence=data.get("average_cadence"),
            suffer_score=data.get("suffer_score"),
            start_time=datetime.fromisoformat(data["start_date_local"].replace("Z", "+00:00")) if data.get("start_date_local") else None,
            description=data.get("description"),
        )
    
    def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None
    
    def __enter__(self) -> "StravaClient":
        return self
    
    def __exit__(self, *args) -> None:
        self.close()
