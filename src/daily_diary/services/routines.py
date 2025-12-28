"""Routines service for managing daily quick-log items."""

import json
from pathlib import Path
from typing import Optional

from ..utils.config import get_settings


class RoutinesService:
    """
    Manages daily routine items for quick logging.
    
    Loads configuration from config/routines.json and provides
    methods for tracking counts throughout the day.
    """
    
    DEFAULT_CONFIG = {
        "caffeine": {
            "title": "☕ Caffeine",
            "items": [
                {"id": "cappuccino", "name": "Cappuccino", "description": "Single shot", "caffeine_mg": 63, "default_count": 1},
                {"id": "espresso", "name": "Espresso", "description": "Single shot", "caffeine_mg": 63, "default_count": 1},
                {"id": "pourover", "name": "Pour Over", "description": "Full cup", "caffeine_mg": 145, "default_count": 1},
            ]
        },
        "alcohol": {
            "title": "🍺 Alcohol",
            "items": [
                {"id": "tallboy", "name": "Tall Boy", "description": "16oz beer", "alcohol_units": 1.3, "default_count": 0},
                {"id": "draft", "name": "Draft Beer", "description": "Pint", "alcohol_units": 1.5, "default_count": 0},
                {"id": "whisky", "name": "Whisky", "description": "Half shots", "alcohol_units": 0.5, "increment": 0.5, "default_count": 0},
            ]
        },
        "medicine_supplements": {
            "title": "💊 Medicine/Supplements", 
            "items": [
                {"id": "fingolimod", "name": "Fingolimod", "dosage": "0.5mg (every other day)", "default_count": 0},
                {"id": "vitamin_d", "name": "Vitamin D", "dosage": "5000 IU", "default_count": 0},
                {"id": "magnesium", "name": "Magnesium", "dosage": "400mg", "default_count": 0},
            ]
        },
        "sleep_factors": {
            "title": "🐱 Sleep Factors",
            "type": "checkbox",
            "items": [
                {"id": "cat_in_room", "name": "Cat slept in my room"},
                {"id": "cat_woke_me", "name": "Cat woke me up"},
            ]
        }
    }
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path("config/routines.json")
        self._config = None
    
    @property
    def config(self) -> dict:
        """Load and cache the routines configuration."""
        if self._config is None:
            self._config = self._load_config()
        return self._config
    
    def _load_config(self) -> dict:
        """Load configuration from file or use defaults."""
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading routines config: {e}")
        return self.DEFAULT_CONFIG
    
    def save_config(self, config: dict) -> None:
        """Save configuration to file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(config, f, indent=2)
        self._config = config
    
    def get_categories(self) -> list[dict]:
        """Get all categories with their items."""
        result = []
        for category_id, category_data in self.config.items():
            result.append({
                "id": category_id,
                "title": category_data.get("title", category_id.title()),
                "type": category_data.get("type", "counter"),  # 'counter' or 'checkbox'
                "items": category_data.get("items", []),
            })
        return result
    
    def get_item(self, item_id: str) -> Optional[dict]:
        """Get a specific item by ID."""
        for category_data in self.config.values():
            for item in category_data.get("items", []):
                if item.get("id") == item_id:
                    return item
        return None
    
    def get_default_counts(self) -> dict[str, float]:
        """Get default counts for all items."""
        counts = {}
        for category_data in self.config.values():
            for item in category_data.get("items", []):
                item_id = item.get("id")
                if item_id:
                    counts[item_id] = item.get("default_count", 0)
        return counts
    
    def calculate_totals(self, counts: dict[str, float]) -> dict:
        """
        Calculate totals (caffeine, alcohol) from counts.
        
        Returns dict with:
        - total_caffeine_mg
        - total_alcohol_units
        - items_consumed (list of consumed items with details)
        """
        total_caffeine = 0
        total_alcohol = 0
        items_consumed = []
        
        for item_id, count in counts.items():
            if count <= 0:
                continue
            
            item = self.get_item(item_id)
            if not item:
                continue
            
            caffeine = item.get("caffeine_mg", 0) * count
            alcohol = item.get("alcohol_units", 0) * count
            
            total_caffeine += caffeine
            total_alcohol += alcohol
            
            items_consumed.append({
                "id": item_id,
                "name": item.get("name"),
                "count": count,
                "caffeine_mg": caffeine,
                "alcohol_units": alcohol,
            })
        
        return {
            "total_caffeine_mg": total_caffeine,
            "total_alcohol_units": total_alcohol,
            "items_consumed": items_consumed,
        }
