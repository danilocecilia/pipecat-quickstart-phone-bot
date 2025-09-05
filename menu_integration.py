#
# DialDish Menu Integration for Pipecat Bot
# This module loads and manages the complete Oishii Windsor menu data
#

import json
import os
from typing import Dict, List, Optional, Tuple
from datetime import datetime

class OishiiMenuManager:
    """Manages the complete Oishii Windsor menu data for the AI assistant"""
    
    def __init__(self, menu_file_path: str = "docs/oishii_windsor_full_menu.json"):
        self.menu_data = self._load_menu(menu_file_path)
        self.categories = list(self.menu_data["menu"].keys())
        self._build_search_index()
    
    def _load_menu(self, file_path: str) -> Dict:
        """Load the menu data from JSON file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            # Fallback to relative path from quickstart-phone-bot directory
            fallback_path = f"../{file_path}"
            with open(fallback_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    
    def _build_search_index(self):
        """Build a searchable index of all menu items"""
        self.item_index = {}
        self.popular_items = []
        
        for category, items in self.menu_data["menu"].items():
            for item in items:
                name = item["name"].lower()
                self.item_index[name] = {
                    "category": category,
                    "item": item
                }
                
                # Identify popular items (this could be based on actual data)
                if any(keyword in name for keyword in [
                    "california", "salmon", "tuna", "dragon", "rainbow", 
                    "philadelphia", "teriyaki", "tempura", "miso"
                ]):
                    self.popular_items.append(item)
    
    def search_items(self, query: str) -> List[Dict]:
        """Search for menu items by name or keyword"""
        query = query.lower()
        results = []
        
        for name, data in self.item_index.items():
            if query in name or any(query in word for word in name.split()):
                results.append(data["item"])
        
        return results
    
    def get_category_items(self, category: str) -> List[Dict]:
        """Get all items from a specific category"""
        return self.menu_data["menu"].get(category, [])
    
    def get_item_by_name(self, item_name: str) -> Optional[Dict]:
        """Get a specific item by exact or fuzzy name match"""
        # Exact match first
        exact_match = self.item_index.get(item_name.lower())
        if exact_match:
            return exact_match["item"]
        
        # Fuzzy search
        results = self.search_items(item_name)
        return results[0] if results else None
    
    def get_vegetarian_items(self) -> List[Dict]:
        """Get all vegetarian menu items"""
        vegetarian_items = []
        for category, items in self.menu_data["menu"].items():
            for item in items:
                if "vegetarian" in item.get("tags", []):
                    vegetarian_items.append(item)
        return vegetarian_items
    
    def get_popular_recommendations(self, limit: int = 5) -> List[Dict]:
        """Get popular item recommendations"""
        return self.popular_items[:limit]
    
    def get_ayce_pricing(self) -> Dict:
        """Get All-You-Can-Eat pricing information"""
        return self.menu_data["ayce_pricing"]
    
    def calculate_total(self, items: List[Dict], include_tax: bool = True) -> float:
        """Calculate total price for a list of items"""
        subtotal = sum(item.get("price", 0) * item.get("quantity", 1) for item in items)
        if include_tax:
            # Ontario HST: 13%
            tax = subtotal * 0.13
            return round(subtotal + tax, 2)
        return round(subtotal, 2)
    
    def format_item_description(self, item: Dict) -> str:
        """Format an item for voice description"""
        name = item["name"]
        price = item["price"]
        desc = item.get("desc", "")
        tags = item.get("tags", [])
        
        description = f"{name} for ${price:.2f}"
        
        if desc:
            description += f" - {desc}"
        
        if "vegetarian" in tags:
            description += " (vegetarian option)"
        
        if "spicy" in tags:
            description += " (spicy)"
            
        return description
    
    def get_menu_summary_for_ai(self) -> str:
        """Generate a comprehensive menu summary for the AI assistant"""
        summary = f"""
OISHII SUSHI WINDSOR MENU KNOWLEDGE:

RESTAURANT INFO:
- Location: 7485 Tecumseh Rd E, Windsor, ON
- Phone: 519-988-1688
- Hours: Mon-Thu 11AM-10PM, Fri-Sat 11AM-10:30PM, Sun 11:30AM-10PM

ALL-YOU-CAN-EAT PRICING:
Weekday Lunch (until 3PM): Adult $27.99, Senior $25.99, Child 7-12 $18.99, Child 3-6 $12.99
Weekend Lunch: Adult $28.99, Senior $26.99, Child 7-12 $19.99, Child 3-6 $13.99
Weekday Dinner: Adult $37.99, Senior $35.99, Child 7-12 $23.99, Child 3-6 $16.99
Weekend Dinner: Adult $39.99, Senior $37.99, Child 7-12 $25.99, Child 3-6 $17.99

MENU CATEGORIES ({len(self.categories)} total):
{', '.join(self.categories)}

POPULAR ITEMS TO RECOMMEND:
"""
        
        # Add popular items from each major category
        popular_by_category = {
            "Appetizers": ["Dumpling (6 pcs) $8.38", "Edamame $8.38", "Tempura Shrimp (5 pcs) $11.98"],
            "Sushi": ["Salmon Sushi $3.98", "Tuna Sushi $3.98", "Eel Sushi $4.28"],
            "Sashimi": ["Salmon Sashimi $3.98", "Tuna Sashimi $3.98", "Yellowtail Sashimi $4.28"],
            "Maki Rolls": ["California Roll $7.28", "Salmon Roll $7.28", "Tuna Roll $7.98"],
            "Special Rolls": ["Dragon Roll $14.98", "Rainbow Roll $13.98", "Philadelphia Roll $12.98"],
            "Teriyaki": ["Chicken Teriyaki $16.98", "Beef Teriyaki $21.98", "Salmon Teriyaki $19.98"]
        }
        
        for category, items in popular_by_category.items():
            summary += f"\n{category}: {', '.join(items)}"
        
        summary += f"""

DIETARY OPTIONS:
- Vegetarian items available (marked with vegetarian tag)
- Fresh sashimi and sushi options
- Cooked options like teriyaki and tempura
- Vegetable rolls and tempura

PRICING NOTES:
- All prices exclude 13% HST tax
- Most rolls: $7-15
- Sushi/Sashimi: $3-5 per piece  
- Appetizers: $8-12
- Entrees: $16-24

ORDERING TIPS:
- Ask about dietary restrictions and allergies
- Suggest All-You-Can-Eat for dine-in if multiple items wanted
- Popular combinations: Miso soup + California roll + Salmon sushi
- Always confirm quantities and modifications
- Calculate tax (13% HST) in final total
"""
        return summary

# Enhanced AI System Prompt with Menu Integration
def get_enhanced_restaurant_prompt(menu_manager: OishiiMenuManager) -> str:
    """Generate the complete AI system prompt with menu knowledge"""
    
    menu_summary = menu_manager.get_menu_summary_for_ai()
    
    return f"""
You are Hana, the friendly AI assistant for Oishii Sushi in Windsor, Ontario. You are an expert on Japanese cuisine and our complete menu.

{menu_summary}

PERSONALITY & APPROACH:
- Warm, professional, and knowledgeable about Japanese cuisine
- Patient and helpful with menu questions
- Make thoughtful recommendations based on customer preferences
- Speak naturally and conversationally

CONVERSATION FLOW:
1. GREETING: "Hello! Thank you for calling Oishii Sushi in Windsor. This is Hana. Are you looking for dine-in, takeout, or delivery today?"

2. ORDER TYPE: Determine dine-in/takeout/delivery and suggest AYCE if appropriate for dine-in

3. MENU ASSISTANCE: 
   - Ask about preferences (raw vs cooked, spicy vs mild, vegetarian needs)
   - Make recommendations from popular items
   - Explain dishes when asked
   - Suggest combinations and add-ons

4. ORDER TAKING:
   - Confirm each item and quantity
   - Ask about modifications/special requests
   - Keep running total and inform customer

5. CUSTOMER DETAILS:
   - Get full name and phone number
   - Confirm order type and any special instructions

6. FINAL CONFIRMATION:
   - Repeat complete order with prices
   - Calculate total with 13% HST tax
   - Provide estimated ready time (15-20 minutes for takeout)
   - Thank customer warmly

MENU EXPERTISE:
- Know exact prices for all items
- Suggest appropriate portions (1-2 rolls per person typically)
- Recommend complementary items (soup with meals, etc.)
- Handle dietary restrictions with vegetarian options
- Explain Japanese terms when needed

PRICING CALCULATION:
- Always calculate 13% HST tax on final total
- Round to nearest cent
- Be transparent about pricing

IMPORTANT RULES:
- Always confirm orders before processing
- Ask about allergies and dietary restrictions  
- Get accurate customer contact information
- When order is complete, say "Let me process this order for you" then provide final summary
- End with: "Thank you! Your order is being prepared. Total is $X.XX including tax, ready in X minutes."

SAMPLE RECOMMENDATIONS:
- First-time customers: California Roll + Miso Soup + Salmon Sushi
- Vegetarian: Vegetable Roll + Tempura Vegetables + Edamame
- Cooked options: Chicken Teriyaki + California Roll
- Sashimi lovers: Assorted Sashimi + Miso Soup
- Large appetite: Suggest All-You-Can-Eat for dine-in
"""

# Menu item extraction for order processing
class OrderProcessor:
    """Process spoken orders into structured data"""
    
    def __init__(self, menu_manager: OishiiMenuManager):
        self.menu = menu_manager
    
    def extract_items_from_conversation(self, conversation_history: List[Dict]) -> List[Dict]:
        """Extract ordered items from conversation history"""
        # This is a simplified version - in production you'd use more sophisticated NLP
        ordered_items = []
        
        # Combine all conversation text
        full_conversation = " ".join([
            msg["content"] for msg in conversation_history 
            if msg["role"] in ["user", "assistant"]
        ]).lower()
        
        # Look for common order patterns and menu items
        # This would be much more sophisticated in production
        item_patterns = [
            ("california roll", "California Roll"),
            ("salmon roll", "Salmon Roll"), 
            ("tuna roll", "Tuna Roll"),
            ("miso soup", "Miso Soup"),
            ("edamame", "Edamame"),
            ("chicken teriyaki", "Chicken Teriyaki"),
            ("salmon sushi", "Salmon Sushi"),
            ("tuna sushi", "Tuna Sushi")
        ]
        
        for pattern, item_name in item_patterns:
            if pattern in full_conversation:
                menu_item = self.menu.get_item_by_name(item_name)
                if menu_item:
                    # Extract quantity (default to 1)
                    quantity = 1
                    # Look for quantity patterns like "two california rolls"
                    import re
                    qty_match = re.search(rf"(\w+)\s+{pattern}", full_conversation)
                    if qty_match:
                        qty_word = qty_match.group(1)
                        qty_map = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
                        quantity = qty_map.get(qty_word, 1)
                    
                    ordered_items.append({
                        "name": menu_item["name"],
                        "price": menu_item["price"],
                        "quantity": quantity,
                        "modifications": ""  # Could extract from conversation
                    })
        
        return ordered_items

# Initialize menu manager (global instance)
menu_manager = None

def initialize_menu_manager(menu_file_path: str = "docs/oishii_windsor_full_menu.json"):
    """Initialize the global menu manager"""
    global menu_manager
    menu_manager = OishiiMenuManager(menu_file_path)
    return menu_manager

def get_menu_manager() -> OishiiMenuManager:
    """Get the global menu manager instance"""
    global menu_manager
    if menu_manager is None:
        menu_manager = initialize_menu_manager()
    return menu_manager
