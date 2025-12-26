"""LLM-powered nutrition estimation service."""

import json
from typing import Optional

from ..utils.config import get_settings


class NutritionEstimator:
    """
    Estimates nutritional content of meals using LLM.
    
    Given a natural language description of a meal (e.g., "burger with fries and a coke"),
    estimates calories, macros, and other nutritional info.
    
    Tries providers in order: Claude (Anthropic) → OpenAI → Heuristic fallback
    """
    
    SYSTEM_PROMPT = """You are a nutrition expert assistant. Given a description of a meal or food item, 
estimate the nutritional content as accurately as possible.

Consider:
- Typical portion sizes unless specified
- Common preparation methods
- Regional variations if context is given
- Include all components mentioned

Return a JSON object with these fields (use null if truly unknown):
{
    "calories": <number>,
    "protein_g": <number>,
    "carbs_g": <number>,
    "fat_g": <number>,
    "fiber_g": <number>,
    "sugar_g": <number>,
    "sodium_mg": <number>,
    "caffeine_mg": <number or 0>,
    "alcohol_units": <number or 0>,
    "water_ml": <number or 0>,
    "confidence": <0.0-1.0 how confident you are>,
    "reasoning": "<brief explanation of your estimate>",
    "components": [
        {"name": "<item>", "calories": <number>, "amount": "<portion>"}
    ]
}

Be conservative in estimates. When uncertain, provide a reasonable range in reasoning.
Common reference points:
- 1 cup rice = ~200 cal
- 1 medium banana = ~105 cal  
- 1 egg = ~70 cal
- 1 oz cheese = ~100 cal
- 1 tbsp olive oil = ~120 cal
- 1 standard drink alcohol = 1 unit

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
            except ImportError as e:
                print(f"[DEBUG] Failed to import anthropic: {e}")
            except Exception as e:
                print(f"[DEBUG] Failed to create Anthropic client: {e}")
        return self._anthropic_client
    
    @property
    def openai_client(self):
        if self._openai_client is None and self.settings.openai_api_key:
            try:
                from openai import OpenAI
                self._openai_client = OpenAI(api_key=self.settings.openai_api_key)
            except ImportError as e:
                print(f"[DEBUG] Failed to import openai: {e}")
            except Exception as e:
                print(f"[DEBUG] Failed to create OpenAI client: {e}")
        return self._openai_client
    
    @property
    def has_claude(self) -> bool:
        return self.settings.anthropic_api_key is not None
    
    @property
    def has_openai(self) -> bool:
        return self.settings.openai_api_key is not None
    
    def estimate(
        self,
        description: str,
        meal_type: Optional[str] = None,
        context: Optional[str] = None,
    ) -> dict:
        """
        Estimate nutritional content of a meal.
        
        Tries providers in order: Claude → OpenAI → Heuristic
        
        Args:
            description: Natural language description of the meal
            meal_type: Optional hint (breakfast, lunch, dinner, snack)
            context: Optional additional context (e.g., "I'm in Italy", "small portion")
        
        Returns:
            Dictionary with nutritional estimates and metadata
        """
        # Build the prompt
        prompt_parts = [f"Meal description: {description}"]
        if meal_type:
            prompt_parts.append(f"Meal type: {meal_type}")
        if context:
            prompt_parts.append(f"Context: {context}")
        
        prompt = "\n".join(prompt_parts)
        
        # Try Claude first
        if self.has_claude:
            result = self._try_claude(prompt)
            if result:
                return result
        
        # Fall back to OpenAI
        if self.has_openai:
            result = self._try_openai(prompt)
            if result:
                return result
        
        # Final fallback to heuristics
        return self._fallback_estimate(description)
    
    def _try_claude(self, prompt: str) -> Optional[dict]:
        """Try estimation with Claude."""
        try:
            import anthropic
            
            if not self.anthropic_client:
                print("[DEBUG] Anthropic client is None")
                return None
            
            response = self.anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[
                    {"role": "user", "content": f"{self.SYSTEM_PROMPT}\n\n{prompt}"}
                ],
            )
            
            # Extract text content
            text = response.content[0].text
            
            # Parse JSON (handle potential markdown code blocks)
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            
            result = json.loads(text.strip())
            result["source"] = "llm"
            result["model"] = "claude-sonnet-4-20250514"
            return result
            
        except anthropic.APIError as e:
            print(f"[DEBUG] Claude API error: {e}")
            return None
        except Exception as e:
            print(f"[DEBUG] Claude estimation error ({type(e).__name__}): {e}")
            return None
    
    def _try_openai(self, prompt: str) -> Optional[dict]:
        """Try estimation with OpenAI."""
        try:
            from openai import OpenAI
            
            if not self.openai_client:
                return None
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=500,
            )
            
            result = json.loads(response.choices[0].message.content)
            result["source"] = "openai"
            result["model"] = "gpt-4o-mini"
            return result
            
        except Exception as e:
            print(f"OpenAI nutrition estimation error: {e}")
            return None
    
    def _fallback_estimate(self, description: str) -> dict:
        """
        Basic heuristic-based estimation when LLMs are unavailable.
        
        Very rough estimates based on keywords.
        """
        description_lower = description.lower()
        
        # Base estimates
        calories = 300
        protein_g = 15
        carbs_g = 30
        fat_g = 10
        
        # Adjust based on keywords
        if any(word in description_lower for word in ["salad", "vegetables", "veggies"]):
            calories = 150
            carbs_g = 15
            fat_g = 5
        elif any(word in description_lower for word in ["burger", "pizza", "fried"]):
            calories = 600
            fat_g = 25
            carbs_g = 50
        elif any(word in description_lower for word in ["steak", "chicken", "fish", "salmon"]):
            calories = 400
            protein_g = 35
            carbs_g = 5
        elif any(word in description_lower for word in ["pasta", "rice", "noodles"]):
            calories = 450
            carbs_g = 60
        elif any(word in description_lower for word in ["sandwich", "wrap"]):
            calories = 400
            carbs_g = 40
        elif any(word in description_lower for word in ["smoothie", "shake"]):
            calories = 250
            carbs_g = 40
            protein_g = 10
        
        # Check for drinks
        caffeine_mg = 0
        if any(word in description_lower for word in ["coffee", "espresso"]):
            caffeine_mg = 95
        elif "tea" in description_lower:
            caffeine_mg = 45
        
        alcohol_units = 0
        if any(word in description_lower for word in ["beer", "wine", "cocktail", "whiskey", "vodka"]):
            alcohol_units = 1.5
            calories += 150
        
        return {
            "calories": calories,
            "protein_g": protein_g,
            "carbs_g": carbs_g,
            "fat_g": fat_g,
            "fiber_g": 5,
            "sugar_g": 10,
            "sodium_mg": 500,
            "caffeine_mg": caffeine_mg,
            "alcohol_units": alcohol_units,
            "water_ml": 0,
            "confidence": 0.3,
            "reasoning": "Fallback heuristic estimate - LLM unavailable",
            "source": "heuristic",
        }
    
    def estimate_batch(self, meals: list[dict]) -> list[dict]:
        """
        Estimate nutrition for multiple meals.
        
        Args:
            meals: List of dicts with 'description' and optional 'meal_type', 'context'
        
        Returns:
            List of nutrition estimates
        """
        return [
            self.estimate(
                m["description"],
                m.get("meal_type"),
                m.get("context"),
            )
            for m in meals
        ]

