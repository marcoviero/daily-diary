"""AI Health Advisor - Doctor's appointment simulation."""

import json
from datetime import date, datetime, timedelta
from typing import Optional

from ..models.entry import DiaryEntry
from ..services.database import AnalyticsDB
from ..services.storage import DiaryStorage
from ..utils.config import get_settings


class HealthAdvisor:
    """
    AI-powered health advisor that analyzes diary data and provides
    personalized health insights and recommendations.
    
    Uses Claude (preferred) or OpenAI as fallback.
    
    IMPORTANT: This is not medical advice. Always consult a real doctor.
    """
    
    SYSTEM_PROMPT = """You are a compassionate and knowledgeable health advisor having a consultation with a patient. 
You have access to their health diary data including symptoms, sleep patterns, activities, meals, and other health metrics.

Your role is to:
1. Listen carefully to their concerns
2. Ask clarifying questions when needed
3. Analyze patterns in their health data
4. Provide thoughtful observations about potential connections
5. Suggest lifestyle modifications or areas to discuss with their doctor
6. Be empathetic and supportive

IMPORTANT GUIDELINES:
- You are NOT a replacement for a real doctor
- Always recommend seeing a healthcare provider for serious concerns
- Don't diagnose conditions - instead, describe patterns and possibilities
- Be clear about uncertainty
- Focus on lifestyle factors, triggers, and patterns you can observe in the data
- For the user's specific condition (neuralgiaform headaches), be aware these are:
  - Brief, severe, stabbing pains often around the eye/temple
  - Can be triggered by various factors including weather changes, sleep, stress
  - Barometric pressure changes are a known trigger for many headache types

When discussing their data:
- Reference specific dates and values when relevant
- Note trends (improving, worsening, stable)
- Identify potential correlations (e.g., poor sleep → symptoms next day)
- Consider weather, especially pressure changes

Start by greeting them warmly and asking what brings them in today."""

    def __init__(self):
        self.settings = get_settings()
        self._anthropic_client = None
        self._openai_client = None
        self._conversation_history = []
        self._health_context = ""  # Store health context for the session
        self._system_prompt_with_context = ""  # Full system prompt with data
        
        # Session metadata
        self._session_id = None
        self._started_at = None
        self._days_reviewed = 30
        self._provider_used = None
    
    @property
    def anthropic_client(self):
        if self._anthropic_client is None and self.settings.anthropic_api_key:
            try:
                import anthropic
                self._anthropic_client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key)
            except ImportError:
                pass
        return self._anthropic_client
    
    @property
    def openai_client(self):
        if self._openai_client is None and self.settings.openai_api_key:
            try:
                from openai import OpenAI
                self._openai_client = OpenAI(api_key=self.settings.openai_api_key)
            except ImportError:
                pass
        return self._openai_client
    
    @property
    def has_claude(self) -> bool:
        return self.settings.anthropic_api_key is not None
    
    @property
    def has_openai(self) -> bool:
        return self.settings.openai_api_key is not None
    
    @property
    def is_configured(self) -> bool:
        return self.has_claude or self.has_openai
    
    def get_health_context(self, days: int = 30) -> str:
        """
        Gather health data from the diary to provide context to the AI.
        
        Returns a formatted string summarizing recent health data.
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        context_parts = [f"=== PATIENT HEALTH DATA (Last {days} days) ===\n"]
        
        # Get entries from storage
        with DiaryStorage(sync_analytics=False) as storage:
            entries = storage.get_entries_in_range(start_date, end_date)
        
        if not entries:
            context_parts.append("No diary entries found for this period.\n")
            return "\n".join(context_parts)
        
        # Summary statistics
        context_parts.append(f"Period: {start_date} to {end_date}")
        context_parts.append(f"Total entries: {len(entries)}\n")
        
        # Symptoms summary
        all_symptoms = []
        for entry in entries:
            for symptom in entry.symptoms:
                all_symptoms.append({
                    "date": entry.entry_date.isoformat(),
                    "type": symptom.display_type,
                    "severity": symptom.severity.value,
                    "location": symptom.display_location,
                    "notes": symptom.notes,
                })
        
        if all_symptoms:
            context_parts.append("--- SYMPTOMS ---")
            for s in all_symptoms[-20:]:  # Last 20 symptoms
                context_parts.append(
                    f"  {s['date']}: {s['type']} (severity {s['severity']}/10) "
                    f"at {s['location']}{' - ' + s['notes'] if s['notes'] else ''}"
                )
            if len(all_symptoms) > 20:
                context_parts.append(f"  ... and {len(all_symptoms) - 20} more symptoms")
            context_parts.append("")
        
        # Sleep data
        sleep_data = []
        for entry in entries:
            if entry.integrations.sleep:
                s = entry.integrations.sleep
                sleep_data.append({
                    "date": entry.entry_date.isoformat(),
                    "score": s.sleep_score,
                    "duration_hrs": round(s.total_sleep_minutes / 60, 1) if s.total_sleep_minutes else None,
                    "hrv": s.hrv_average,
                    "deep_pct": round(s.deep_sleep_minutes / s.total_sleep_minutes * 100) if s.total_sleep_minutes and s.deep_sleep_minutes else None,
                })
        
        if sleep_data:
            context_parts.append("--- SLEEP (Last 14 nights) ---")
            for s in sleep_data[-14:]:
                parts = [f"  {s['date']}: Score {s['score']}"]
                if s['duration_hrs']:
                    parts.append(f"{s['duration_hrs']}h")
                if s['hrv']:
                    parts.append(f"HRV {s['hrv']:.0f}")
                if s['deep_pct']:
                    parts.append(f"Deep {s['deep_pct']}%")
                context_parts.append(", ".join(parts))
            context_parts.append("")
        
        # Weather data (especially pressure)
        weather_data = []
        for entry in entries:
            if entry.integrations.weather:
                w = entry.integrations.weather
                weather_data.append({
                    "date": entry.entry_date.isoformat(),
                    "pressure": w.pressure_hpa,
                    "temp": w.temp_avg_c,
                    "description": w.description,
                })
        
        if weather_data:
            context_parts.append("--- WEATHER/PRESSURE (Last 14 days) ---")
            for w in weather_data[-14:]:
                context_parts.append(
                    f"  {w['date']}: {w['pressure']} hPa, {w['temp']:.0f}°C, {w['description']}"
                )
            context_parts.append("")
        
        # Activities
        activity_data = []
        for entry in entries:
            for activity in entry.integrations.activities or []:
                activity_data.append({
                    "date": entry.entry_date.isoformat(),
                    "type": activity.activity_type,
                    "name": activity.name,
                    "duration": activity.duration_minutes,
                    "hr_avg": activity.average_heart_rate,
                })
        
        if activity_data:
            context_parts.append("--- ACTIVITIES (Last 14) ---")
            for a in activity_data[-14:]:
                parts = [f"  {a['date']}: {a['name'] or a['type']}"]
                if a['duration']:
                    parts.append(f"{a['duration']:.0f}min")
                if a['hr_avg']:
                    parts.append(f"HR {a['hr_avg']:.0f}")
                context_parts.append(", ".join(parts))
            context_parts.append("")
        
        # Meals with potential triggers
        trigger_meals = []
        for entry in entries:
            for meal in entry.meals:
                if meal.contains_alcohol or meal.contains_caffeine or meal.trigger_foods:
                    trigger_meals.append({
                        "date": entry.entry_date.isoformat(),
                        "meal": meal.description[:50],
                        "alcohol": meal.alcohol_units if meal.contains_alcohol else 0,
                        "caffeine": meal.contains_caffeine,
                        "triggers": meal.trigger_foods,
                    })
        
        if trigger_meals:
            context_parts.append("--- POTENTIAL DIETARY TRIGGERS ---")
            for m in trigger_meals[-10:]:
                flags = []
                if m['alcohol']:
                    flags.append(f"{m['alcohol']} alcohol units")
                if m['caffeine']:
                    flags.append("caffeine")
                if m['triggers']:
                    flags.append(f"triggers: {', '.join(m['triggers'])}")
                context_parts.append(f"  {m['date']}: {m['meal']} ({', '.join(flags)})")
            context_parts.append("")
        
        # Wellbeing scores
        wellbeing_data = []
        for entry in entries:
            if entry.overall_wellbeing:
                wellbeing_data.append({
                    "date": entry.entry_date.isoformat(),
                    "wellbeing": entry.overall_wellbeing,
                    "energy": entry.energy_level,
                    "stress": entry.stress_level,
                    "mood": entry.mood,
                })
        
        if wellbeing_data:
            context_parts.append("--- WELLBEING SCORES (Last 14 days) ---")
            for w in wellbeing_data[-14:]:
                parts = [f"  {w['date']}: Wellbeing {w['wellbeing']}/10"]
                if w['energy']:
                    parts.append(f"Energy {w['energy']}/10")
                if w['stress']:
                    parts.append(f"Stress {w['stress']}/10")
                if w['mood']:
                    parts.append(f"Mood: {w['mood']}")
                context_parts.append(", ".join(parts))
            context_parts.append("")
        
        # Notes
        notes = []
        for entry in entries:
            if entry.general_notes:
                notes.append(f"  {entry.entry_date}: {entry.general_notes[:200]}...")
        
        if notes:
            context_parts.append("--- RECENT NOTES ---")
            context_parts.extend(notes[-5:])
            context_parts.append("")
        
        context_parts.append("=== END OF HEALTH DATA ===")
        
        return "\n".join(context_parts)
    
    def start_consultation(self, days: int = 30, session_id: str = None) -> tuple[str, str]:
        """
        Start a new consultation session.
        
        Returns:
            Tuple of (greeting message, provider used)
        """
        import uuid
        
        self._conversation_history = []
        self._session_id = session_id or str(uuid.uuid4())
        self._started_at = datetime.now()
        self._days_reviewed = days
        
        # Get health context and store it for the session
        self._health_context = self.get_health_context(days)
        
        # Build and store system prompt with context
        self._system_prompt_with_context = f"{self.SYSTEM_PROMPT}\n\n{self._health_context}"
        
        # Get initial greeting
        response, provider = self._get_response(
            self._system_prompt_with_context,
            "Please greet me and ask what brings me in today. Briefly mention that you've reviewed my recent health data.",
            is_first_message=True
        )
        
        self._provider_used = provider
        
        return response, provider
    
    def send_message(self, user_message: str) -> tuple[str, str]:
        """
        Send a message and get a response.
        
        Args:
            user_message: The user's message
        
        Returns:
            Tuple of (response message, provider used)
        """
        # Add user message to history
        self._conversation_history.append({
            "role": "user",
            "content": user_message
        })
        
        # Use the stored system prompt with health context
        # Fall back to base prompt if consultation wasn't started properly
        system_prompt = self._system_prompt_with_context or self.SYSTEM_PROMPT
        
        # Get response
        response, provider = self._get_response(system_prompt, user_message)
        
        # Add assistant response to history
        self._conversation_history.append({
            "role": "assistant",
            "content": response
        })
        
        return response, provider
    
    def _get_response(
        self, 
        system_prompt: str, 
        user_message: str,
        is_first_message: bool = False
    ) -> tuple[str, str]:
        """Get response from Claude or OpenAI."""
        
        # Try Claude first
        if self.has_claude:
            response = self._try_claude(system_prompt, user_message, is_first_message)
            if response:
                return response, "claude"
        
        # Fall back to OpenAI
        if self.has_openai:
            response = self._try_openai(system_prompt, user_message, is_first_message)
            if response:
                return response, "openai"
        
        return "I'm sorry, but I'm unable to respond right now. Please check your API configuration.", "none"
    
    def _try_claude(
        self, 
        system_prompt: str, 
        user_message: str,
        is_first_message: bool = False
    ) -> Optional[str]:
        """Try to get response from Claude."""
        try:
            import anthropic
            
            if not self.anthropic_client:
                return None
            
            # Build messages
            if is_first_message:
                messages = [{"role": "user", "content": user_message}]
            else:
                messages = self._conversation_history.copy()
            
            response = self.anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1500,
                system=system_prompt,
                messages=messages,
            )
            
            return response.content[0].text
            
        except Exception as e:
            print(f"Claude health advisor error: {e}")
            return None
    
    def _try_openai(
        self, 
        system_prompt: str, 
        user_message: str,
        is_first_message: bool = False
    ) -> Optional[str]:
        """Try to get response from OpenAI."""
        try:
            from openai import OpenAI
            
            if not self.openai_client:
                return None
            
            # Build messages
            messages = [{"role": "system", "content": system_prompt}]
            
            if is_first_message:
                messages.append({"role": "user", "content": user_message})
            else:
                messages.extend(self._conversation_history)
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                max_tokens=1500,
                temperature=0.7,
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"OpenAI health advisor error: {e}")
            return None
    
    def get_conversation_history(self) -> list[dict]:
        """Get the current conversation history."""
        return self._conversation_history.copy()
    
    def clear_history(self) -> None:
        """Clear conversation history and health context."""
        self._conversation_history = []
        self._health_context = ""
        self._system_prompt_with_context = ""
        self._session_id = None
        self._started_at = None
        self._provider_used = None
    
    def end_consultation(self) -> Optional[dict]:
        """
        End the consultation and generate a summary.
        
        Returns:
            Dictionary with consultation summary, or None if failed
        """
        if not self._conversation_history or not self._started_at:
            return None
        
        # Generate summary using AI
        summary_data = self._generate_summary()
        
        # Save to database
        try:
            from .database import AnalyticsDB
            import json
            
            with AnalyticsDB() as db:
                db.save_consultation(
                    consultation_id=self._session_id,
                    consultation_date=date.today(),
                    started_at=self._started_at,
                    ended_at=datetime.now(),
                    days_reviewed=self._days_reviewed,
                    chief_complaint=summary_data.get('chief_complaint'),
                    summary=summary_data.get('summary', ''),
                    key_findings=summary_data.get('key_findings'),
                    patterns_identified=summary_data.get('patterns_identified'),
                    recommendations=summary_data.get('recommendations'),
                    triggers_discussed=summary_data.get('triggers_discussed'),
                    follow_up_actions=summary_data.get('follow_up_actions'),
                    message_count=len([m for m in self._conversation_history if m['role'] == 'user']),
                    provider=self._provider_used or 'unknown',
                    conversation_json=json.dumps(self._conversation_history),
                )
        except Exception as e:
            print(f"Error saving consultation: {e}")
        
        # Clear session
        result = {
            'session_id': self._session_id,
            'summary': summary_data,
            'message_count': len(self._conversation_history),
        }
        
        self.clear_history()
        
        return result
    
    def _generate_summary(self) -> dict:
        """Generate a structured summary of the consultation."""
        
        summary_prompt = """Based on our consultation conversation, please provide a structured summary in JSON format with these fields:
{
    "chief_complaint": "The main reason/concern the patient came in for (1-2 sentences)",
    "summary": "A brief narrative summary of the consultation (2-3 sentences)",
    "key_findings": "Important observations from the health data discussed (bullet points as a single string)",
    "patterns_identified": "Any patterns noticed in symptoms, sleep, triggers, etc. (bullet points as a single string)",
    "recommendations": "Lifestyle or behavioral suggestions discussed (bullet points as a single string)",
    "triggers_discussed": "Potential triggers that were identified or discussed (comma-separated list)",
    "follow_up_actions": "Any follow-up actions the patient should take (bullet points as a single string)"
}

Return ONLY the JSON object, no other text. If a field doesn't apply, use null."""

        # Add summary request to get response
        response, _ = self._get_response(
            self._system_prompt_with_context,
            summary_prompt,
        )
        
        # Parse JSON response
        try:
            import json
            
            # Handle potential markdown code blocks
            text = response
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            
            return json.loads(text.strip())
        except Exception as e:
            print(f"Error parsing summary: {e}")
            # Return basic summary if parsing fails
            return {
                "summary": "Consultation completed. Summary generation failed.",
                "chief_complaint": None,
                "key_findings": None,
                "patterns_identified": None,
                "recommendations": None,
                "triggers_discussed": None,
                "follow_up_actions": None,
            }
