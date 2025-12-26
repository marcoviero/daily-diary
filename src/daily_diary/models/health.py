"""Health-related data models."""

from datetime import datetime, time
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Severity(int, Enum):
    """Pain/symptom severity scale (0-10)."""
    NONE = 0
    MINIMAL = 1
    MILD = 2
    MILD_MODERATE = 3
    MODERATE = 4
    MODERATE_SEVERE = 5
    SEVERE = 6
    VERY_SEVERE = 7
    INTENSE = 8
    VERY_INTENSE = 9
    WORST_POSSIBLE = 10


class SymptomType(str, Enum):
    """Common symptom types for quick selection."""
    HEADACHE = "headache"
    HEADACHE_NEURALGIAFORM = "neuralgiaform_headache"
    JOINT_PAIN = "joint_pain"
    MUSCLE_PAIN = "muscle_pain"
    FATIGUE = "fatigue"
    NAUSEA = "nausea"
    DIZZINESS = "dizziness"
    NUMBNESS = "numbness"
    TINGLING = "tingling"
    STIFFNESS = "stiffness"
    WEAKNESS = "weakness"
    OTHER = "other"


class BodyLocation(str, Enum):
    """Body locations for symptom/incident tracking."""
    HEAD = "head"
    NECK = "neck"
    SHOULDER_LEFT = "shoulder_left"
    SHOULDER_RIGHT = "shoulder_right"
    ARM_LEFT = "arm_left"
    ARM_RIGHT = "arm_right"
    ELBOW_LEFT = "elbow_left"
    ELBOW_RIGHT = "elbow_right"
    WRIST_LEFT = "wrist_left"
    WRIST_RIGHT = "wrist_right"
    HAND_LEFT = "hand_left"
    HAND_RIGHT = "hand_right"
    UPPER_BACK = "upper_back"
    LOWER_BACK = "lower_back"
    CHEST = "chest"
    ABDOMEN = "abdomen"
    HIP_LEFT = "hip_left"
    HIP_RIGHT = "hip_right"
    KNEE_LEFT = "knee_left"
    KNEE_RIGHT = "knee_right"
    ANKLE_LEFT = "ankle_left"
    ANKLE_RIGHT = "ankle_right"
    FOOT_LEFT = "foot_left"
    FOOT_RIGHT = "foot_right"
    OTHER = "other"


class Symptom(BaseModel):
    """A symptom or health complaint."""
    
    type: SymptomType
    custom_type: Optional[str] = None  # For SymptomType.OTHER
    severity: Severity
    location: Optional[BodyLocation] = None
    custom_location: Optional[str] = None  # For BodyLocation.OTHER
    onset_time: Optional[time] = None
    duration_minutes: Optional[int] = None
    notes: Optional[str] = None
    
    # Potential triggers noted by user
    suspected_triggers: list[str] = Field(default_factory=list)
    
    @property
    def display_type(self) -> str:
        """Human-readable symptom type."""
        if self.type == SymptomType.OTHER and self.custom_type:
            return self.custom_type
        return self.type.value.replace("_", " ").title()
    
    @property
    def display_location(self) -> str | None:
        """Human-readable location."""
        if self.location is None:
            return None
        if self.location == BodyLocation.OTHER and self.custom_location:
            return self.custom_location
        return self.location.value.replace("_", " ").title()


class IncidentType(str, Enum):
    """Types of physical incidents."""
    FALL = "fall"
    BUMP = "bump"
    CUT = "cut"
    STRAIN = "strain"
    SPRAIN = "sprain"
    OVEREXERTION = "overexertion"
    COLLISION = "collision"
    OTHER = "other"


class Incident(BaseModel):
    """A physical incident that might cause future symptoms."""
    
    type: IncidentType
    custom_type: Optional[str] = None
    location: BodyLocation
    custom_location: Optional[str] = None
    severity: Severity  # How bad was the incident itself
    time_occurred: Optional[time] = None
    description: str
    immediate_symptoms: list[str] = Field(default_factory=list)
    
    @property
    def display_type(self) -> str:
        """Human-readable incident type."""
        if self.type == IncidentType.OTHER and self.custom_type:
            return self.custom_type
        return self.type.value.title()


class MealType(str, Enum):
    """Meal types."""
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"
    BEVERAGE = "beverage"


class Meal(BaseModel):
    """A meal or food/drink consumption."""
    
    meal_type: MealType
    time_consumed: Optional[time] = None
    description: str
    
    # Specific items that might be triggers
    contains_alcohol: bool = False
    alcohol_units: Optional[float] = None  # Standard drink units
    contains_caffeine: bool = False
    contains_common_triggers: list[str] = Field(default_factory=list)  # e.g., MSG, aged cheese
    
    notes: Optional[str] = None
