"""Main diary entry model."""

from datetime import date, datetime
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from .health import Incident, Meal, Symptom
from .integrations import DailyIntegrations


class DiaryEntry(BaseModel):
    """A single day's diary entry."""
    
    # Identity
    id: str = Field(default_factory=lambda: str(uuid4()))
    entry_date: date
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    # Health tracking
    symptoms: list[Symptom] = Field(default_factory=list)
    incidents: list[Incident] = Field(default_factory=list)
    meals: list[Meal] = Field(default_factory=list)
    
    # Integrated data (auto-fetched)
    integrations: DailyIntegrations = Field(default_factory=DailyIntegrations)
    
    # Free-form notes
    morning_notes: Optional[str] = None
    evening_notes: Optional[str] = None
    general_notes: Optional[str] = None
    
    # Overall daily assessment
    overall_wellbeing: Optional[int] = None  # 1-10 scale
    energy_level: Optional[int] = None  # 1-10 scale
    stress_level: Optional[int] = None  # 1-10 scale
    mood: Optional[str] = None  # Free text or predefined
    
    # Entry completeness
    is_complete: bool = False
    
    def add_symptom(self, symptom: Symptom) -> None:
        """Add a symptom to this entry."""
        self.symptoms.append(symptom)
        self.updated_at = datetime.now()
    
    def add_incident(self, incident: Incident) -> None:
        """Add an incident to this entry."""
        self.incidents.append(incident)
        self.updated_at = datetime.now()
    
    def add_meal(self, meal: Meal) -> None:
        """Add a meal to this entry."""
        self.meals.append(meal)
        self.updated_at = datetime.now()
    
    def mark_complete(self) -> None:
        """Mark the entry as complete."""
        self.is_complete = True
        self.updated_at = datetime.now()
    
    @property
    def has_symptoms(self) -> bool:
        return len(self.symptoms) > 0
    
    @property
    def has_incidents(self) -> bool:
        return len(self.incidents) > 0
    
    @property
    def worst_symptom_severity(self) -> int:
        """Return the worst symptom severity for the day."""
        if not self.symptoms:
            return 0
        return max(s.severity.value for s in self.symptoms)
    
    @property
    def alcohol_consumed(self) -> bool:
        """Check if any alcohol was consumed."""
        return any(m.contains_alcohol for m in self.meals)
    
    @property
    def total_alcohol_units(self) -> float:
        """Total alcohol units consumed."""
        return sum(m.alcohol_units or 0 for m in self.meals if m.contains_alcohol)
    
    def summary(self) -> str:
        """Generate a brief summary of the entry."""
        parts = [f"Entry for {self.entry_date.strftime('%A, %B %d, %Y')}"]
        
        if self.overall_wellbeing:
            parts.append(f"Wellbeing: {self.overall_wellbeing}/10")
        
        if self.symptoms:
            worst = max(self.symptoms, key=lambda s: s.severity.value)
            parts.append(f"Symptoms: {len(self.symptoms)} logged (worst: {worst.display_type} at {worst.severity.value}/10)")
        
        if self.incidents:
            parts.append(f"Incidents: {len(self.incidents)} logged")
        
        if self.integrations.activities:
            mins = self.integrations.total_activity_minutes
            parts.append(f"Activity: {mins:.0f} min")
        
        if self.integrations.sleep and self.integrations.sleep.sleep_score:
            parts.append(f"Sleep score: {self.integrations.sleep.sleep_score}")
        
        return " | ".join(parts)
