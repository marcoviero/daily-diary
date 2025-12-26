"""Configuration management."""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
    # Weather API
    openweather_api_key: Optional[str] = None
    
    # Strava API
    strava_client_id: Optional[str] = None
    strava_client_secret: Optional[str] = None
    strava_refresh_token: Optional[str] = None
    
    # Oura API
    oura_access_token: Optional[str] = None
    
    # OpenAI (for Whisper transcription)
    openai_api_key: Optional[str] = None
    
    # Location defaults (Portland, OR)
    default_latitude: float = Field(default=45.5152)
    default_longitude: float = Field(default=-122.6784)
    
    # Data storage
    data_dir: Path = Field(default=Path("data"))
    
    @property
    def has_weather(self) -> bool:
        return self.openweather_api_key is not None
    
    @property
    def has_strava(self) -> bool:
        return all([
            self.strava_client_id,
            self.strava_client_secret,
            self.strava_refresh_token,
        ])
    
    @property
    def has_oura(self) -> bool:
        return self.oura_access_token is not None
    
    @property
    def has_transcription(self) -> bool:
        return self.openai_api_key is not None


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
