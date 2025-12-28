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
    
    # Oura API (OAuth2 or Personal Access Token)
    oura_access_token: Optional[str] = None  # PAT (legacy) or leave blank for OAuth2
    oura_client_id: Optional[str] = None     # OAuth2
    oura_client_secret: Optional[str] = None # OAuth2
    oura_refresh_token: Optional[str] = None # OAuth2
    
    # OpenAI (optional - for Whisper API if faster-whisper not installed)
    openai_api_key: Optional[str] = None
    
    # Transcription settings
    transcription_local_only: bool = Field(default=True)  # Don't fall back to OpenAI
    
    # Anthropic (for nutrition estimation and health advisor)
    anthropic_api_key: Optional[str] = None
    
    # Location defaults (Portland, OR)
    default_latitude: float = Field(default=45.5152)
    default_longitude: float = Field(default=-122.6784)
    
    # Data storage
    data_dir: Path = Field(default=Path("data"))
    
    @property
    def has_weather(self) -> bool:
        # Open-Meteo is free and requires no API key, just lat/lon
        return self.default_latitude is not None and self.default_longitude is not None
    
    @property
    def has_strava(self) -> bool:
        return all([
            self.strava_client_id,
            self.strava_client_secret,
            self.strava_refresh_token,
        ])
    
    @property
    def has_oura(self) -> bool:
        # Either PAT or OAuth2 credentials
        has_pat = self.oura_access_token is not None
        has_oauth = all([
            self.oura_client_id,
            self.oura_client_secret,
            self.oura_refresh_token,
        ])
        return has_pat or has_oauth
    
    @property
    def has_transcription(self) -> bool:
        return self.openai_api_key is not None


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
