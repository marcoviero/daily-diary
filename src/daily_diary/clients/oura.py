"""Oura Ring API client."""

from datetime import date, datetime
from typing import Optional

import httpx

from ..models.integrations import SleepData
from ..utils.config import Settings, get_settings


class OuraClient:
    """
    Client for fetching sleep and readiness data from Oura Ring.
    
    Supports both:
    - Personal Access Tokens (legacy, being deprecated)
    - OAuth2 (recommended)
    """
    
    API_URL = "https://api.ouraring.com/v2"
    AUTH_URL = "https://api.ouraring.com/oauth/token"
    
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._client: Optional[httpx.Client] = None
        self._access_token: Optional[str] = None
    
    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=30.0)
        return self._client
    
    @property
    def is_configured(self) -> bool:
        # Either PAT or OAuth2 credentials
        return self.settings.has_oura
    
    def _get_access_token(self) -> Optional[str]:
        """Get a valid access token (refresh if using OAuth2)."""
        # If we have a PAT, use it directly
        if self.settings.oura_access_token:
            return self.settings.oura_access_token
        
        # If we have OAuth2 credentials, refresh the token
        if self.settings.oura_client_id and self.settings.oura_refresh_token:
            return self._refresh_oauth_token()
        
        return None
    
    def _refresh_oauth_token(self) -> Optional[str]:
        """Refresh OAuth2 access token."""
        if self._access_token:
            return self._access_token
            
        try:
            response = self.client.post(
                self.AUTH_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": self.settings.oura_client_id,
                    "client_secret": self.settings.oura_client_secret,
                    "refresh_token": self.settings.oura_refresh_token,
                },
            )
            response.raise_for_status()
            data = response.json()
            self._access_token = data.get("access_token")
            return self._access_token
        except httpx.HTTPError as e:
            print(f"Oura OAuth error: {e}")
            return None
    
    def _get_headers(self) -> dict[str, str]:
        """Get authorization headers."""
        token = self._get_access_token()
        return {"Authorization": f"Bearer {token}"} if token else {}
    
    def get_sleep_for_date(self, target_date: date) -> Optional[SleepData]:
        """
        Fetch sleep data for a specific date.
        
        Note: Oura's 'day' field = the date you woke up.
        Sleep for night of Dec 23→24 has day='2025-12-24'.
        
        The API end_date is exclusive, so we query [target_date, target_date+1).
        """
        if not self.is_configured:
            return None
        
        token = self._get_access_token()
        if not token:
            print("Oura: Could not get access token")
            return None
        
        from datetime import timedelta
        end_date = target_date + timedelta(days=1)
        
        try:
            # Get detailed sleep data
            response = self.client.get(
                f"{self.API_URL}/usercollection/sleep",
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "start_date": target_date.isoformat(),
                    "end_date": end_date.isoformat(),
                },
            )
            response.raise_for_status()
            data = response.json()
            
            if not data.get("data"):
                return None
            
            # Get the main sleep period (longest one)
            sleep_periods = data["data"]
            main_sleep = max(sleep_periods, key=lambda x: x.get("total_sleep_duration", 0))
            
            # Also fetch daily_sleep for the score
            score_response = self.client.get(
                f"{self.API_URL}/usercollection/daily_sleep",
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "start_date": target_date.isoformat(),
                    "end_date": end_date.isoformat(),
                },
            )
            score_response.raise_for_status()
            score_data = score_response.json()
            
            sleep_score = None
            if score_data.get("data"):
                sleep_score = score_data["data"][0].get("score")
            
            return self._parse_sleep(main_sleep, sleep_score)
        except httpx.HTTPError as e:
            print(f"Oura API error: {e}")
            return None
    
    def get_readiness_for_date(self, target_date: date) -> Optional[int]:
        """Fetch readiness score for a specific date."""
        if not self.is_configured:
            return None
        
        token = self._get_access_token()
        if not token:
            return None
        
        # End date is exclusive in Oura API, so add 1 day
        from datetime import timedelta
        end_date = target_date + timedelta(days=1)
        
        try:
            response = self.client.get(
                f"{self.API_URL}/usercollection/daily_readiness",
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "start_date": target_date.isoformat(),
                    "end_date": end_date.isoformat(),
                },
            )
            response.raise_for_status()
            data = response.json()
            
            if not data.get("data"):
                return None
            
            return data["data"][0].get("score")
        except httpx.HTTPError as e:
            print(f"Oura API error: {e}")
            return None
    
    def _parse_sleep(self, data: dict, sleep_score: Optional[int] = None) -> SleepData:
        """Parse Oura API response into SleepData model."""
        # Duration fields are in seconds in API v2
        def seconds_to_minutes(seconds: Optional[int]) -> Optional[int]:
            return seconds // 60 if seconds else None
        
        return SleepData(
            bedtime=datetime.fromisoformat(data["bedtime_start"]) if data.get("bedtime_start") else None,
            wake_time=datetime.fromisoformat(data["bedtime_end"]) if data.get("bedtime_end") else None,
            total_sleep_minutes=seconds_to_minutes(data.get("total_sleep_duration")),
            rem_sleep_minutes=seconds_to_minutes(data.get("rem_sleep_duration")),
            deep_sleep_minutes=seconds_to_minutes(data.get("deep_sleep_duration")),
            light_sleep_minutes=seconds_to_minutes(data.get("light_sleep_duration")),
            awake_minutes=seconds_to_minutes(data.get("awake_time")),
            sleep_score=sleep_score,  # From daily_sleep endpoint
            efficiency_percent=data.get("efficiency"),
            lowest_heart_rate=data.get("lowest_heart_rate"),
            average_heart_rate=data.get("average_heart_rate"),
            hrv_average=data.get("average_hrv"),
            respiratory_rate=data.get("average_breath"),
            restless_periods=data.get("restless_periods"),
        )
    
    def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None
    
    def __enter__(self) -> "OuraClient":
        return self
    
    def __exit__(self, *args) -> None:
        self.close()
