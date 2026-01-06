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
    
    SYSTEM_PROMPT = """You are a nutrition expert. Estimate the nutritional content of meals accurately.

CRITICAL RULES:
1. ITEMIZE FIRST: List every food component separately with its portion and calories BEFORE summing
2. PORTION MATTERS: A "salad" can be 150-800 cal. A "sandwich" can be 300-900 cal. Think about realistic portions.
3. NO DEFAULT ESTIMATES: Do not fall back to generic "medium meal" values. Each meal is unique.
4. SHOW YOUR WORK: Your reasoning must explain each component's contribution

WARNING: Do NOT default to ~485 calories. This is a known failure mode.
Calculate from components FIRST, then sum. If your total happens to be 480-490,
double-check your component math - you may be anchoring to a default.

PORTION SIZE GUIDELINES:
- Restaurant portions are typically 1.5-2x home portions
- "A bowl of" = ~1.5-2 cups
- "A plate of" = filling a dinner plate
- Unspecified meat = ~4-6 oz cooked
- Unspecified pasta = ~2 cups cooked
- Coffee shop pastry = larger than homemade
- "Half" of something = literally half the standard size

CALORIE REFERENCE (use these exact values):
Proteins: egg=70, chicken breast 6oz=280, salmon 6oz=350, ground beef 4oz=290, tofu 4oz=90
Carbs: bread slice=80, rice 1cup=200, pasta 1cup=220, potato medium=160, banana=105, bagel whole=280
Fats: butter 1tbsp=100, olive oil 1tbsp=120, avocado half=160, cheese 1oz=110, peanut butter 1tbsp=95
Drinks: coffee black=5, latte 12oz=190, orange juice 8oz=110, soda 12oz=140
Common meals: Big Mac=550, Chipotle burrito=1000, slice cheese pizza=285, ramen bowl=450

THINK STEP BY STEP:
1. What are ALL the components? (Don't forget oils, sauces, sides, drinks)
2. What's the likely portion of each?
3. Look up or calculate each component's calories from the reference values
4. Sum totals
5. Sanity check: Does this match what you'd expect for this meal type?

Return ONLY this JSON:
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
    "confidence": <0.0-1.0>,
    "reasoning": "<MUST list each component with portion and calories, then explain total>",
    "components": [
        {"name": "<item>", "calories": <number>, "amount": "<specific portion>"}
    ]
}

The "components" array is REQUIRED and must itemize every part of the meal."""
    
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
                max_tokens=800,
                temperature=0.7,
                messages=[
                    {"role": "user", "content": f"{self.SYSTEM_PROMPT}\n\n{prompt}"}
                ],
            )
            
            # Extract text content
            text = response.content[0].text
            
            # Try multiple JSON extraction strategies
            json_text = None
            
            # Strategy 1: Look for ```json blocks
            if "```json" in text:
                json_text = text.split("```json")[1].split("```")[0]
            # Strategy 2: Look for any ``` blocks
            elif "```" in text:
                json_text = text.split("```")[1].split("```")[0]
            # Strategy 3: Find JSON object boundaries
            elif "{" in text and "}" in text:
                start = text.find("{")
                end = text.rfind("}") + 1
                json_text = text[start:end]
            else:
                json_text = text
            
            try:
                result = json.loads(json_text.strip())
                result["source"] = "llm"
                result["model"] = "claude-sonnet-4-20250514"
                return result
            except json.JSONDecodeError as e:
                # Print what we got for debugging
                print(f"\n[DEBUG] JSON parse failed at position {e.pos}")
                print(f"[DEBUG] Error: {e.msg}")
                print(f"[DEBUG] === RAW RESPONSE START ===")
                print(text)
                print(f"[DEBUG] === RAW RESPONSE END ===")
                print(f"[DEBUG] === EXTRACTED JSON START ===")
                print(json_text)
                print(f"[DEBUG] === EXTRACTED JSON END ===\n")
                return None
            
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
                temperature=0.7,
                max_tokens=800,
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
        
        Uses keyword matching for rough estimates.
        """
        description_lower = description.lower()
        
        # Start with nothing and build up
        calories = 0
        protein_g = 0
        carbs_g = 0
        fat_g = 0
        fiber_g = 0
        components = []
        
        # Check for proteins
        if any(word in description_lower for word in ["chicken", "turkey"]):
            calories += 250
            protein_g += 30
            fat_g += 8
            components.append("poultry ~250cal")
        if any(word in description_lower for word in ["beef", "steak", "burger patty"]):
            calories += 300
            protein_g += 25
            fat_g += 20
            components.append("beef ~300cal")
        if any(word in description_lower for word in ["salmon", "fish", "tuna"]):
            calories += 280
            protein_g += 30
            fat_g += 12
            components.append("fish ~280cal")
        if "egg" in description_lower:
            count = 2 if "eggs" in description_lower else 1
            calories += 70 * count
            protein_g += 6 * count
            fat_g += 5 * count
            components.append(f"egg(s) ~{70*count}cal")
        
        # Check for soups/stews/chili
        if any(word in description_lower for word in ["chili", "chilli"]):
            calories += 400
            protein_g += 25
            carbs_g += 30
            fat_g += 18
            fiber_g += 8
            components.append("bowl of chili ~400cal")
        elif any(word in description_lower for word in ["soup", "stew"]):
            calories += 250
            protein_g += 12
            carbs_g += 25
            fat_g += 10
            components.append("bowl of soup/stew ~250cal")
        
        # Check for carbs
        if any(word in description_lower for word in ["rice", "fried rice"]):
            calories += 200
            carbs_g += 45
            components.append("rice ~200cal")
        if any(word in description_lower for word in ["pasta", "spaghetti", "noodles"]):
            calories += 220
            carbs_g += 45
            components.append("pasta ~220cal")
        if any(word in description_lower for word in ["bread", "toast"]):
            calories += 80
            carbs_g += 15
            components.append("bread ~80cal")
        if "bagel" in description_lower:
            mult = 0.5 if "half" in description_lower else 1.0
            calories += int(280 * mult)
            carbs_g += int(55 * mult)
            components.append(f"bagel ~{int(280*mult)}cal")
        if any(word in description_lower for word in ["potato", "fries"]):
            calories += 200
            carbs_g += 35
            fat_g += 8
            components.append("potato/fries ~200cal")
        
        # Italian snacks/crackers
        if "taralli" in description_lower:
            # ~40 cal each, check for count
            import re
            match = re.search(r'(\d+)\s*taralli', description_lower)
            count = int(match.group(1)) if match else 5
            calories += 40 * count
            carbs_g += 5 * count
            fat_g += 2 * count
            components.append(f"taralli x{count} ~{40*count}cal")
        if any(word in description_lower for word in ["crackers", "cracker"]):
            calories += 120
            carbs_g += 20
            fat_g += 4
            components.append("crackers ~120cal")
        if any(word in description_lower for word in ["chips", "crisps"]):
            calories += 150
            carbs_g += 15
            fat_g += 10
            components.append("chips ~150cal")
        
        # Check for fats/additions
        if any(word in description_lower for word in ["peanut butter", "pb"]):
            tbsp = 2  # assume 2 tbsp
            calories += 190
            protein_g += 8
            fat_g += 16
            components.append("peanut butter 2tbsp ~190cal")
        if any(word in description_lower for word in ["butter", "buttered"]):
            calories += 100
            fat_g += 11
            components.append("butter ~100cal")
        if any(word in description_lower for word in ["cheese", "cheesy"]):
            calories += 110
            protein_g += 7
            fat_g += 9
            components.append("cheese ~110cal")
        if "avocado" in description_lower:
            calories += 160
            fat_g += 15
            fiber_g += 5
            components.append("avocado ~160cal")
        
        # Check for vegetables (low cal)
        if any(word in description_lower for word in ["salad", "vegetables", "veggies", "greens"]):
            calories += 50
            carbs_g += 10
            fiber_g += 3
            components.append("vegetables ~50cal")
        
        # Check for complete meals
        if any(word in description_lower for word in ["burger", "hamburger"]) and "patty" not in description_lower:
            calories = 550
            protein_g = 25
            carbs_g = 45
            fat_g = 30
            components = ["complete burger ~550cal"]
        if "pizza" in description_lower:
            slices = 2 if "slices" in description_lower else 1
            calories = 285 * slices
            protein_g = 12 * slices
            carbs_g = 35 * slices
            fat_g = 10 * slices
            components = [f"pizza {slices} slice(s) ~{285*slices}cal"]
        if "burrito" in description_lower:
            calories = 800
            protein_g = 30
            carbs_g = 80
            fat_g = 35
            components = ["burrito ~800cal"]
        if "sandwich" in description_lower:
            calories = 450
            protein_g = 20
            carbs_g = 40
            fat_g = 22
            components = ["sandwich ~450cal"]
        
        # Check for drinks
        caffeine_mg = 0
        if any(word in description_lower for word in ["coffee", "espresso", "americano"]):
            if "latte" in description_lower or "cappuccino" in description_lower:
                calories += 150
                components.append("latte ~150cal")
            else:
                calories += 5
                components.append("black coffee ~5cal")
            caffeine_mg = 95
        elif "tea" in description_lower:
            calories += 5
            caffeine_mg = 45
            components.append("tea ~5cal")
        
        alcohol_units = 0
        if any(word in description_lower for word in ["beer"]):
            alcohol_units = 1.5
            calories += 150
            carbs_g += 13
            components.append("beer ~150cal")
        elif any(word in description_lower for word in ["wine"]):
            alcohol_units = 1.5
            calories += 125
            components.append("wine ~125cal")
        elif any(word in description_lower for word in ["cocktail", "margarita", "martini"]):
            alcohol_units = 2
            calories += 200
            components.append("cocktail ~200cal")
        elif any(word in description_lower for word in ["whiskey", "vodka", "rum", "gin", "shot"]):
            alcohol_units = 1
            calories += 100
            components.append("spirit ~100cal")
        
        # If nothing matched, provide minimal estimate
        if calories == 0:
            calories = 200
            protein_g = 8
            carbs_g = 25
            fat_g = 8
            components = ["unrecognized food ~200cal estimate"]
        
        return {
            "calories": calories,
            "protein_g": protein_g,
            "carbs_g": carbs_g,
            "fat_g": fat_g,
            "fiber_g": fiber_g,
            "sugar_g": int(carbs_g * 0.3),  # rough estimate
            "sodium_mg": 400 + (calories // 2),  # rough estimate
            "caffeine_mg": caffeine_mg,
            "alcohol_units": alcohol_units,
            "water_ml": 0,
            "confidence": 0.3,
            "reasoning": f"Heuristic estimate (LLM unavailable). Components: {', '.join(components)}",
            "source": "heuristic",
            "components": [{"name": c, "calories": 0, "amount": "estimated"} for c in components],
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
