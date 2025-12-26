"""Voice transcription service using OpenAI Whisper."""

from pathlib import Path
from typing import Optional

from openai import OpenAI

from ..utils.config import Settings, get_settings


class TranscriptionService:
    """
    Transcribe audio to text using OpenAI's Whisper API.
    
    Supports voice diary entries for hands-free logging.
    """
    
    SUPPORTED_FORMATS = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"}
    
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._client: Optional[OpenAI] = None
    
    @property
    def client(self) -> OpenAI:
        """Get the OpenAI client."""
        if self._client is None:
            self._client = OpenAI(api_key=self.settings.openai_api_key)
        return self._client
    
    @property
    def is_configured(self) -> bool:
        return self.settings.has_transcription
    
    def transcribe_file(self, audio_path: Path) -> Optional[str]:
        """
        Transcribe an audio file to text.
        
        Args:
            audio_path: Path to the audio file
            
        Returns:
            Transcribed text, or None if transcription failed
        """
        if not self.is_configured:
            print("Transcription not configured - set OPENAI_API_KEY")
            return None
        
        if not audio_path.exists():
            print(f"Audio file not found: {audio_path}")
            return None
        
        if audio_path.suffix.lower() not in self.SUPPORTED_FORMATS:
            print(f"Unsupported audio format: {audio_path.suffix}")
            return None
        
        try:
            with open(audio_path, "rb") as audio_file:
                response = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="text",
                    language="en",  # Optimize for English
                    prompt="Health diary entry. Symptoms, pain levels, headaches, exercise, meals, incidents.",
                )
            return response
        except Exception as e:
            print(f"Transcription error: {e}")
            return None
    
    def transcribe_with_timestamps(
        self,
        audio_path: Path,
    ) -> Optional[dict]:
        """
        Transcribe with word-level timestamps.
        
        Useful for longer recordings where you might want to
        extract specific time segments.
        """
        if not self.is_configured or not audio_path.exists():
            return None
        
        try:
            with open(audio_path, "rb") as audio_file:
                response = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json",
                    timestamp_granularities=["word"],
                    language="en",
                )
            return response.model_dump()
        except Exception as e:
            print(f"Transcription error: {e}")
            return None
