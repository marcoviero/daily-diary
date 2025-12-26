"""Local storage service using TinyDB."""

from datetime import date
from pathlib import Path
from typing import Optional

from tinydb import Query, TinyDB

from ..models.entry import DiaryEntry
from ..utils.config import Settings, get_settings


class DiaryStorage:
    """
    Local storage for diary entries using TinyDB.
    
    Data is stored as JSON in the data directory.
    """
    
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._db: Optional[TinyDB] = None
    
    @property
    def db_path(self) -> Path:
        """Path to the database file."""
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        return self.settings.data_dir / "diary.json"
    
    @property
    def db(self) -> TinyDB:
        """Get the TinyDB instance."""
        if self._db is None:
            self._db = TinyDB(self.db_path)
        return self._db
    
    def save_entry(self, entry: DiaryEntry) -> None:
        """Save or update a diary entry."""
        Entry = Query()
        
        # Convert to dict for storage
        entry_dict = entry.model_dump(mode="json")
        
        # Upsert based on entry_date
        existing = self.db.search(Entry.entry_date == entry.entry_date.isoformat())
        
        if existing:
            self.db.update(entry_dict, Entry.entry_date == entry.entry_date.isoformat())
        else:
            self.db.insert(entry_dict)
    
    def get_entry(self, entry_date: date) -> Optional[DiaryEntry]:
        """Get an entry by date."""
        Entry = Query()
        results = self.db.search(Entry.entry_date == entry_date.isoformat())
        
        if results:
            return DiaryEntry.model_validate(results[0])
        return None
    
    def get_or_create_entry(self, entry_date: date) -> DiaryEntry:
        """Get an existing entry or create a new one."""
        entry = self.get_entry(entry_date)
        if entry is None:
            entry = DiaryEntry(entry_date=entry_date)
            self.save_entry(entry)
        return entry
    
    def get_recent_entries(self, days: int = 30) -> list[DiaryEntry]:
        """Get entries from the last N days."""
        all_entries = self.db.all()
        
        # Parse and sort by date
        entries = [DiaryEntry.model_validate(e) for e in all_entries]
        entries.sort(key=lambda e: e.entry_date, reverse=True)
        
        return entries[:days]
    
    def get_entries_in_range(
        self,
        start_date: date,
        end_date: date,
    ) -> list[DiaryEntry]:
        """Get all entries within a date range."""
        Entry = Query()
        
        results = self.db.search(
            (Entry.entry_date >= start_date.isoformat()) &
            (Entry.entry_date <= end_date.isoformat())
        )
        
        entries = [DiaryEntry.model_validate(e) for e in results]
        entries.sort(key=lambda e: e.entry_date)
        return entries
    
    def search_entries(self, query: str) -> list[DiaryEntry]:
        """
        Search entries by text content.
        
        Searches notes, symptom descriptions, and incident descriptions.
        """
        query_lower = query.lower()
        results = []
        
        for entry_dict in self.db.all():
            entry = DiaryEntry.model_validate(entry_dict)
            
            # Search in notes
            searchable_text = " ".join(filter(None, [
                entry.morning_notes,
                entry.evening_notes,
                entry.general_notes,
            ])).lower()
            
            # Search in symptoms
            for symptom in entry.symptoms:
                searchable_text += f" {symptom.display_type} {symptom.notes or ''}"
            
            # Search in incidents
            for incident in entry.incidents:
                searchable_text += f" {incident.display_type} {incident.description}"
            
            if query_lower in searchable_text.lower():
                results.append(entry)
        
        results.sort(key=lambda e: e.entry_date, reverse=True)
        return results
    
    def delete_entry(self, entry_date: date) -> bool:
        """Delete an entry by date."""
        Entry = Query()
        removed = self.db.remove(Entry.entry_date == entry_date.isoformat())
        return len(removed) > 0
    
    def close(self) -> None:
        """Close the database connection."""
        if self._db:
            self._db.close()
            self._db = None
    
    def __enter__(self) -> "DiaryStorage":
        return self
    
    def __exit__(self, *args) -> None:
        self.close()
