"""Voice transcription service using OpenAI Whisper or local faster-whisper."""

import subprocess
from pathlib import Path
from typing import Optional

from ..utils.config import Settings, get_settings


class TranscriptionService:
    """
    Transcribe audio to text using Whisper.
    
    Tries in order:
    1. Local faster-whisper (free, runs on your machine)
    2. OpenAI Whisper API (paid, requires OPENAI_API_KEY)
    
    Supports voice diary entries for hands-free logging.
    """
    
    SUPPORTED_FORMATS = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm", ".ogg"}
    
    def __init__(self, settings: Optional[Settings] = None, local_only: bool = False):
        self.settings = settings or get_settings()
        self.local_only = local_only  # If True, never fall back to OpenAI
        self._openai_client = None
        self._local_model = None
        self._local_model_checked = False
        self._local_load_error: Optional[str] = None
    
    @property
    def openai_client(self):
        """Get the OpenAI client."""
        if self._openai_client is None and self.settings.openai_api_key:
            try:
                from openai import OpenAI
                self._openai_client = OpenAI(api_key=self.settings.openai_api_key)
            except ImportError:
                pass
        return self._openai_client
    
    @property
    def local_model(self):
        """Get local faster-whisper model (lazy loaded)."""
        if not self._local_model_checked:
            self._local_model_checked = True
            try:
                from faster_whisper import WhisperModel
                # Use 'base' model - good balance of speed/accuracy
                # Options: tiny, base, small, medium, large-v2
                self._local_model = WhisperModel("base", device="cpu", compute_type="int8")
                print("✓ Local Whisper model loaded successfully")
            except ImportError:
                self._local_load_error = "faster-whisper not installed. Install with: uv pip install faster-whisper"
                print(f"⚠ {self._local_load_error}")
            except Exception as e:
                self._local_load_error = f"Could not load local Whisper model: {e}"
                print(f"⚠ {self._local_load_error}")
        return self._local_model
    
    @property
    def has_local(self) -> bool:
        return self.local_model is not None
    
    @property
    def has_openai(self) -> bool:
        return self.settings.openai_api_key is not None and not self.local_only
    
    @property
    def is_configured(self) -> bool:
        return self.has_local or self.has_openai
    
    def transcribe_file(self, audio_path: Path) -> Optional[str]:
        """
        Transcribe an audio file to text.
        
        Tries local transcription first, falls back to OpenAI API.
        
        Args:
            audio_path: Path to the audio file
            
        Returns:
            Transcribed text, or None if transcription failed
        """
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        if audio_path.suffix.lower() not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported audio format: {audio_path.suffix}")
        
        # Convert webm to wav for better compatibility with local model
        converted_path = None
        file_to_use = audio_path
        
        if audio_path.suffix.lower() == ".webm":
            converted_path = self._convert_audio(audio_path)
            if converted_path:
                file_to_use = converted_path
        
        try:
            # Try local transcription first (free!)
            if self.has_local:
                result = self._transcribe_local(file_to_use)
                if result:
                    return result
            
            # If local-only mode, don't fall back to OpenAI
            if self.local_only:
                error_msg = "Local transcription failed."
                if self._local_load_error:
                    error_msg += f" {self._local_load_error}"
                raise ValueError(error_msg)
            
            # Fall back to OpenAI API
            if self.has_openai:
                result = self._transcribe_openai(file_to_use)
                if result:
                    return result
            
            if not self.is_configured:
                raise ValueError(
                    "No transcription method available. Either:\n"
                    "1. Install faster-whisper: uv pip install faster-whisper\n"
                    "2. Set OPENAI_API_KEY in .env"
                )
            
            return None
            
        finally:
            # Clean up converted file
            if converted_path and converted_path.exists():
                try:
                    converted_path.unlink()
                except Exception:
                    pass
    
    def _convert_audio(self, audio_path: Path) -> Optional[Path]:
        """Convert audio to wav format using ffmpeg."""
        try:
            converted_path = audio_path.with_suffix(".wav")
            result = subprocess.run(
                [
                    "ffmpeg", "-i", str(audio_path), 
                    "-y",  # Overwrite
                    "-vn",  # No video
                    "-acodec", "pcm_s16le",  # WAV format
                    "-ar", "16000",  # 16kHz sample rate (what Whisper expects)
                    "-ac", "1",  # Mono
                    str(converted_path)
                ],
                capture_output=True,
                timeout=30
            )
            if result.returncode == 0 and converted_path.exists():
                return converted_path
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # ffmpeg not available
            pass
        return None
    
    def _transcribe_local(self, audio_path: Path) -> Optional[str]:
        """Transcribe using local faster-whisper model."""
        try:
            segments, info = self.local_model.transcribe(
                str(audio_path),
                language="en",
                initial_prompt="Health diary entry. Symptoms, pain levels, headaches, exercise, meals, incidents.",
                vad_filter=True,  # Filter out silence
            )
            
            # Combine all segments
            text = " ".join(segment.text.strip() for segment in segments)
            return text if text else None
            
        except Exception as e:
            print(f"Local transcription error: {e}")
            return None
    
    def _transcribe_openai(self, audio_path: Path) -> Optional[str]:
        """Transcribe using OpenAI Whisper API."""
        try:
            with open(audio_path, "rb") as audio_file:
                response = self.openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="text",
                    language="en",
                    prompt="Health diary entry. Symptoms, pain levels, headaches, exercise, meals, incidents.",
                )
            return response
        except Exception as e:
            error_str = str(e)
            if "quota" in error_str.lower() or "exceeded" in error_str.lower():
                raise RuntimeError(f"OpenAI API quota exceeded. Check your billing at platform.openai.com")
            elif "invalid_api_key" in error_str.lower():
                raise RuntimeError("Invalid OpenAI API key. Check OPENAI_API_KEY in .env")
            else:
                raise RuntimeError(f"OpenAI API error: {e}")
    
    def transcribe_with_timestamps(
        self,
        audio_path: Path,
    ) -> Optional[dict]:
        """
        Transcribe with word-level timestamps.
        
        Only available with local model or OpenAI API.
        """
        if not audio_path.exists():
            return None
        
        # Try local first
        if self.has_local:
            try:
                segments, info = self.local_model.transcribe(
                    str(audio_path),
                    language="en",
                    word_timestamps=True,
                )
                
                words = []
                for segment in segments:
                    for word in segment.words:
                        words.append({
                            "word": word.word,
                            "start": word.start,
                            "end": word.end,
                        })
                
                return {
                    "text": " ".join(w["word"] for w in words),
                    "words": words,
                    "language": info.language,
                    "duration": info.duration,
                }
            except Exception as e:
                print(f"Local transcription error: {e}")
        
        # Fall back to OpenAI (unless local_only)
        if self.has_openai and not self.local_only:
            try:
                with open(audio_path, "rb") as audio_file:
                    response = self.openai_client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        response_format="verbose_json",
                        timestamp_granularities=["word"],
                        language="en",
                    )
                return response.model_dump()
            except Exception as e:
                print(f"OpenAI transcription error: {e}")
        
        return None
