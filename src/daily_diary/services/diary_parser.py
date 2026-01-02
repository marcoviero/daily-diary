"""LLM-powered diary entry parser.

Parses natural language voice notes into structured diary data.
"""

import json
from datetime import time
from typing import Optional

from ..models.health import (
    BodyLocation,
    Incident,
    IncidentType,
    Meal,
    MealType,
    Medication,
    MedicationForm,
    Severity,
    Supplement,
    Symptom,
    SymptomType,
)
from ..utils.config import get_settings


class DiaryParser:
    """
    Parses natural language diary entries into structured data.
    
    Uses Claude (preferred) or OpenAI to extract:
    - Meals and nutrition
    - Medications taken
    - Supplements taken
    - Symptoms experienced
    - Incidents/injuries
    - Overall wellbeing metrics
    - Sleep quality notes
    """
    
    SYSTEM_PROMPT = """You are a health diary assistant that extracts structured data from natural language diary entries.

Given a transcribed voice note about someone's day, extract ALL relevant health information into a structured JSON format.

IMPORTANT: Extract everything mentioned, even if brief. Be thorough but accurate - only extract what's actually stated or clearly implied.

Return a JSON object with these fields (omit fields with no data, use null for unknown values):

{
    "meals": [
        {
            "meal_type": "breakfast|lunch|dinner|snack|beverage",
            "time": "HH:MM" or null,
            "description": "what was eaten/drunk",
            "contains_alcohol": true/false,
            "alcohol_units": number or null,
            "contains_caffeine": true/false,
            "calories": estimated number or null,
            "protein_g": number or null,
            "carbs_g": number or null,
            "fat_g": number or null
        }
    ],
    "medications": [
        {
            "name": "medication name",
            "dosage": "e.g., 100mg, 2 tablets",
            "form": "tablet|capsule|liquid|injection|topical|inhaler|patch|drops|spray|other",
            "time": "HH:MM" or null,
            "reason": "why it was taken"
        }
    ],
    "supplements": [
        {
            "name": "supplement name",
            "dosage": "e.g., 1000 IU, 400mg",
            "time": "HH:MM" or null
        }
    ],
    "symptoms": [
        {
            "type": "headache|neuralgiaform_headache|joint_pain|muscle_pain|fatigue|nausea|dizziness|numbness|tingling|stiffness|weakness|other",
            "custom_type": "description if type is other",
            "severity": 1-10,
            "location": "head|neck|shoulder_left|shoulder_right|arm_left|arm_right|upper_back|lower_back|chest|abdomen|other",
            "custom_location": "description if location is other",
            "onset_time": "HH:MM" or null,
            "duration_minutes": number or null,
            "notes": "additional details",
            "suspected_triggers": ["trigger1", "trigger2"]
        }
    ],
    "incidents": [
        {
            "type": "fall|bump|cut|strain|sprain|overexertion|collision|other",
            "custom_type": "description if type is other",
            "location": "body location",
            "severity": 1-10,
            "time": "HH:MM" or null,
            "description": "what happened"
        }
    ],
    "wellbeing": {
        "overall": 1-10 or null,
        "energy": 1-10 or null,
        "stress": 1-10 or null,
        "mood": "description" or null
    },
    "sleep_notes": "any mentions of sleep quality, duration, issues",
    "exercise_notes": "any mentions of exercise or physical activity",
    "general_notes": "anything else mentioned that doesn't fit above categories"
}

Guidelines:
- For neuralgiaform headaches, use type "neuralgiaform_headache"
- Common medications: Sumatriptan, Ibuprofen, Tylenol/Acetaminophen, Aspirin, etc.
- Common supplements: Vitamin D, Magnesium, Fish Oil, B12, Iron, etc.
- If times are relative ("this morning", "around noon"), estimate reasonable times
- Severity should be interpreted: "mild"=2-3, "moderate"=4-5, "severe"=7-8, "worst"=9-10
- For caffeine: coffee, tea, energy drinks all contain caffeine
- For alcohol: beer, wine, spirits, cocktails

Return ONLY the JSON object, no other text."""

    def __init__(self):
        self.settings = get_settings()
        self._anthropic_client = None
        self._openai_client = None
    
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
    
    def parse(self, text: str) -> dict:
        """
        Parse a natural language diary entry into structured data.
        
        Args:
            text: The transcribed voice note or typed entry
            
        Returns:
            Dictionary with extracted data and metadata
        """
        if not self.is_configured:
            return {
                "success": False,
                "error": "No LLM provider configured",
                "raw_text": text,
            }
        
        # Try Claude first
        if self.has_claude:
            result = self._try_claude(text)
            if result:
                return self._process_result(result, text, "claude")
        
        # Fall back to OpenAI
        if self.has_openai:
            result = self._try_openai(text)
            if result:
                return self._process_result(result, text, "openai")
        
        return {
            "success": False,
            "error": "All LLM providers failed",
            "raw_text": text,
        }
    
    def _try_claude(self, text: str) -> Optional[dict]:
        """Try parsing with Claude."""
        try:
            response = self.anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                messages=[
                    {"role": "user", "content": f"{self.SYSTEM_PROMPT}\n\nDiary entry to parse:\n\n{text}"}
                ],
            )
            
            response_text = response.content[0].text
            
            # Parse JSON
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]
            
            return json.loads(response_text.strip())
            
        except Exception as e:
            print(f"Claude parsing error: {e}")
            return None
    
    def _try_openai(self, text: str) -> Optional[dict]:
        """Try parsing with OpenAI."""
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": f"Diary entry to parse:\n\n{text}"},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=2000,
            )
            
            return json.loads(response.choices[0].message.content)
            
        except Exception as e:
            print(f"OpenAI parsing error: {e}")
            return None
    
    def _process_result(self, data: dict, raw_text: str, provider: str) -> dict:
        """Process the LLM result into structured model objects."""
        result = {
            "success": True,
            "provider": provider,
            "raw_text": raw_text,
            "meals": [],
            "medications": [],
            "supplements": [],
            "symptoms": [],
            "incidents": [],
            "wellbeing": data.get("wellbeing", {}),
            "sleep_notes": data.get("sleep_notes"),
            "exercise_notes": data.get("exercise_notes"),
            "general_notes": data.get("general_notes"),
        }
        
        # Process meals
        for meal_data in data.get("meals", []):
            try:
                meal = Meal(
                    meal_type=MealType(meal_data.get("meal_type", "snack")),
                    time_consumed=self._parse_time(meal_data.get("time")),
                    description=meal_data.get("description", ""),
                    contains_alcohol=meal_data.get("contains_alcohol", False),
                    alcohol_units=meal_data.get("alcohol_units"),
                    contains_caffeine=meal_data.get("contains_caffeine", False),
                    calories=meal_data.get("calories"),
                    protein_g=meal_data.get("protein_g"),
                    carbs_g=meal_data.get("carbs_g"),
                    fat_g=meal_data.get("fat_g"),
                )
                result["meals"].append(meal)
            except Exception as e:
                print(f"Error processing meal: {e}")
        
        # Process medications
        for med_data in data.get("medications", []):
            try:
                form = None
                if med_data.get("form"):
                    try:
                        form = MedicationForm(med_data["form"])
                    except ValueError:
                        form = MedicationForm.OTHER
                
                med = Medication(
                    name=med_data.get("name", "Unknown"),
                    dosage=med_data.get("dosage"),
                    form=form,
                    time_taken=self._parse_time(med_data.get("time")),
                    reason=med_data.get("reason"),
                )
                result["medications"].append(med)
            except Exception as e:
                print(f"Error processing medication: {e}")
        
        # Process supplements
        for supp_data in data.get("supplements", []):
            try:
                supp = Supplement(
                    name=supp_data.get("name", "Unknown"),
                    dosage=supp_data.get("dosage"),
                    time_taken=self._parse_time(supp_data.get("time")),
                )
                result["supplements"].append(supp)
            except Exception as e:
                print(f"Error processing supplement: {e}")
        
        # Process symptoms
        for symp_data in data.get("symptoms", []):
            try:
                symp_type = SymptomType.OTHER
                if symp_data.get("type"):
                    try:
                        symp_type = SymptomType(symp_data["type"])
                    except ValueError:
                        pass
                
                location = None
                if symp_data.get("location"):
                    try:
                        location = BodyLocation(symp_data["location"])
                    except ValueError:
                        location = BodyLocation.OTHER
                
                severity_val = symp_data.get("severity", 5)
                if isinstance(severity_val, int) and 0 <= severity_val <= 10:
                    severity = Severity(severity_val)
                else:
                    severity = Severity.MODERATE
                
                symp = Symptom(
                    type=symp_type,
                    custom_type=symp_data.get("custom_type"),
                    severity=severity,
                    location=location,
                    custom_location=symp_data.get("custom_location"),
                    onset_time=self._parse_time(symp_data.get("onset_time")),
                    duration_minutes=symp_data.get("duration_minutes"),
                    notes=symp_data.get("notes"),
                    suspected_triggers=symp_data.get("suspected_triggers", []),
                )
                result["symptoms"].append(symp)
            except Exception as e:
                print(f"Error processing symptom: {e}")
        
        # Process incidents
        for inc_data in data.get("incidents", []):
            try:
                inc_type = IncidentType.OTHER
                if inc_data.get("type"):
                    try:
                        inc_type = IncidentType(inc_data["type"])
                    except ValueError:
                        pass
                
                location = BodyLocation.OTHER
                if inc_data.get("location"):
                    try:
                        location = BodyLocation(inc_data["location"])
                    except ValueError:
                        pass
                
                severity_val = inc_data.get("severity", 5)
                if isinstance(severity_val, int) and 0 <= severity_val <= 10:
                    severity = Severity(severity_val)
                else:
                    severity = Severity.MODERATE
                
                inc = Incident(
                    type=inc_type,
                    custom_type=inc_data.get("custom_type"),
                    location=location,
                    custom_location=inc_data.get("custom_location"),
                    severity=severity,
                    time_occurred=self._parse_time(inc_data.get("time")),
                    description=inc_data.get("description", ""),
                )
                result["incidents"].append(inc)
            except Exception as e:
                print(f"Error processing incident: {e}")
        
        return result
    
    def _parse_time(self, time_str: Optional[str]) -> Optional[time]:
        """Parse a time string into a time object."""
        if not time_str:
            return None
        
        try:
            # Handle HH:MM format
            if ":" in time_str:
                parts = time_str.split(":")
                return time(int(parts[0]), int(parts[1]))
        except Exception:
            pass
        
        return None
    
    def apply_to_entry(self, parsed_data: dict, entry, entry_date=None) -> dict:
        """
        Apply parsed data to a diary entry.
        
        Args:
            parsed_data: Result from parse()
            entry: DiaryEntry to update
            entry_date: Date for database operations (required for meals)
            
        Returns:
            Summary of what was added
        """
        if not parsed_data.get("success"):
            return {"error": parsed_data.get("error", "Parsing failed")}
        
        summary = {
            "meals_added": 0,
            "medications_added": 0,
            "supplements_added": 0,
            "symptoms_added": 0,
            "incidents_added": 0,
            "wellbeing_updated": False,
        }
        
        # Add meals - these go to SQLite, not JSON
        if parsed_data.get("meals") and entry_date:
            from .database import AnalyticsDB
            from .nutrition import NutritionEstimator
            
            estimator = NutritionEstimator()
            
            with AnalyticsDB() as db:
                for meal in parsed_data.get("meals", []):
                    # Get nutrition from parsed data or estimate
                    if isinstance(meal, Meal):
                        description = meal.description
                        meal_type = meal.meal_type.value if meal.meal_type else "snack"
                        time_consumed = meal.time_consumed
                        notes = meal.notes
                        
                        # Use parsed nutrition or estimate
                        nutrition = {
                            'calories': meal.calories,
                            'protein_g': meal.protein_g,
                            'carbs_g': meal.carbs_g,
                            'fat_g': meal.fat_g,
                            'fiber_g': meal.fiber_g,
                            'caffeine_mg': None,
                            'alcohol_units': meal.alcohol_units,
                            'estimation_confidence': 'parsed',
                            'reasoning': 'Extracted from voice note',
                        }
                        
                        # If no nutrition data, estimate it
                        if not nutrition['calories']:
                            estimated = estimator.estimate(description)
                            nutrition.update(estimated)
                    else:
                        # Dict from parser
                        description = meal.get('description', '')
                        meal_type = meal.get('meal_type', 'snack')
                        notes = meal.get('notes')
                        
                        # Parse time string to time object
                        time_consumed = None
                        time_str = meal.get('time')
                        if time_str:
                            try:
                                from datetime import datetime as dt
                                time_consumed = dt.strptime(time_str, "%H:%M").time()
                            except (ValueError, TypeError):
                                pass
                        
                        nutrition = {
                            'calories': meal.get('calories'),
                            'protein_g': meal.get('protein_g'),
                            'carbs_g': meal.get('carbs_g'),
                            'fat_g': meal.get('fat_g'),
                            'fiber_g': meal.get('fiber_g'),
                            'caffeine_mg': None,
                            'alcohol_units': meal.get('alcohol_units'),
                            'estimation_confidence': 'parsed',
                            'reasoning': 'Extracted from voice note',
                        }
                        
                        if not nutrition['calories']:
                            estimated = estimator.estimate(description)
                            nutrition.update(estimated)
                    
                    db.add_meal_with_nutrition(
                        entry_date=entry_date,
                        meal_type=meal_type,
                        description=description,
                        nutrition=nutrition,
                        time_consumed=time_consumed,
                        notes=notes,
                    )
                    summary["meals_added"] += 1
        
        # Add medications
        for med in parsed_data.get("medications", []):
            entry.add_medication(med)
            summary["medications_added"] += 1
        
        # Add supplements
        for supp in parsed_data.get("supplements", []):
            entry.add_supplement(supp)
            summary["supplements_added"] += 1
        
        # Add symptoms
        for symp in parsed_data.get("symptoms", []):
            entry.add_symptom(symp)
            summary["symptoms_added"] += 1
        
        # Add incidents
        for inc in parsed_data.get("incidents", []):
            entry.add_incident(inc)
            summary["incidents_added"] += 1
        
        # Update wellbeing if provided
        wellbeing = parsed_data.get("wellbeing", {})
        if wellbeing:
            if wellbeing.get("overall") and not entry.overall_wellbeing:
                entry.overall_wellbeing = wellbeing["overall"]
                summary["wellbeing_updated"] = True
            if wellbeing.get("energy") and not entry.energy_level:
                entry.energy_level = wellbeing["energy"]
                summary["wellbeing_updated"] = True
            if wellbeing.get("stress") and not entry.stress_level:
                entry.stress_level = wellbeing["stress"]
                summary["wellbeing_updated"] = True
            if wellbeing.get("mood") and not entry.mood:
                entry.mood = wellbeing["mood"]
                summary["wellbeing_updated"] = True
        
        # Append any extra notes
        extra_notes = []
        if parsed_data.get("sleep_notes"):
            extra_notes.append(f"Sleep: {parsed_data['sleep_notes']}")
        if parsed_data.get("exercise_notes"):
            extra_notes.append(f"Exercise: {parsed_data['exercise_notes']}")
        if parsed_data.get("general_notes"):
            extra_notes.append(parsed_data["general_notes"])
        
        if extra_notes:
            if entry.general_notes:
                entry.general_notes += "\n\n" + "\n".join(extra_notes)
            else:
                entry.general_notes = "\n".join(extra_notes)
        
        return summary
