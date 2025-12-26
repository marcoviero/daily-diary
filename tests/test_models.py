"""Tests for data models."""

from datetime import date

import pytest

from daily_diary.models import DiaryEntry, Symptom
from daily_diary.models.health import Severity, SymptomType


class TestSymptom:
    """Tests for the Symptom model."""
    
    def test_create_symptom(self):
        """Test basic symptom creation."""
        symptom = Symptom(
            type=SymptomType.HEADACHE,
            severity=Severity.MODERATE,
        )
        assert symptom.type == SymptomType.HEADACHE
        assert symptom.severity == Severity.MODERATE
        assert symptom.severity.value == 4
    
    def test_display_type(self):
        """Test human-readable type display."""
        symptom = Symptom(
            type=SymptomType.HEADACHE_NEURALGIAFORM,
            severity=Severity.SEVERE,
        )
        assert symptom.display_type == "Neuralgiaform Headache"
    
    def test_custom_type(self):
        """Test custom symptom type."""
        symptom = Symptom(
            type=SymptomType.OTHER,
            custom_type="Tinnitus",
            severity=Severity.MILD,
        )
        assert symptom.display_type == "Tinnitus"


class TestDiaryEntry:
    """Tests for the DiaryEntry model."""
    
    def test_create_entry(self):
        """Test basic entry creation."""
        entry = DiaryEntry(entry_date=date.today())
        assert entry.entry_date == date.today()
        assert entry.symptoms == []
        assert entry.is_complete is False
    
    def test_add_symptom(self):
        """Test adding symptoms to entry."""
        entry = DiaryEntry(entry_date=date.today())
        symptom = Symptom(
            type=SymptomType.HEADACHE,
            severity=Severity.MODERATE,
        )
        
        entry.add_symptom(symptom)
        
        assert len(entry.symptoms) == 1
        assert entry.has_symptoms is True
        assert entry.worst_symptom_severity == 4
    
    def test_summary(self):
        """Test entry summary generation."""
        entry = DiaryEntry(
            entry_date=date(2024, 12, 25),
            overall_wellbeing=7,
        )
        summary = entry.summary()
        
        assert "December 25, 2024" in summary
        assert "7/10" in summary
