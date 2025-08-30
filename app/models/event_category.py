import json
import os
from datetime import datetime
from typing import List, Dict, Optional

EVENT_CATEGORIES_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "event_categories.json")

class EventCategory:
    def __init__(self, id: str, name: str, description: str = "", created_at: str = None, is_event: bool = False):
        self.id = id
        self.name = name
        self.description = description
        self.created_at = created_at or datetime.now().isoformat()
        self.is_event = is_event

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "is_event": self.is_event
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'EventCategory':
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            created_at=data.get("created_at"),
            is_event=data.get("is_event", False)
        )

def load_event_categories() -> List[EventCategory]:
    """Load event categories from JSON file"""
    if not os.path.exists(EVENT_CATEGORIES_PATH):
        # Create default categories
        default_categories = [
            EventCategory("general", "General", "General knowledge and information", is_event=False),
            EventCategory("training", "Training", "Training materials and courses", is_event=False),
            EventCategory("policies", "Policies", "Policies and procedures", is_event=False),
            EventCategory("faqs", "FAQs", "Frequently asked questions", is_event=False),
            EventCategory("events", "Events", "Event schedules and information", is_event=True),
            EventCategory("classes", "Classes", "Training classes and courses", is_event=True),
            EventCategory("exams", "Exams", "Certification exams and testing", is_event=True),
            EventCategory("orientation", "Orientation", "New student orientation sessions", is_event=True),
            EventCategory("externships", "Externships", "Clinical externship opportunities", is_event=True),
            EventCategory("workshops", "Workshops", "Skills workshops and training sessions", is_event=True)
        ]
        save_event_categories(default_categories)
        return default_categories
    
    try:
        with open(EVENT_CATEGORIES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return [EventCategory.from_dict(cat) for cat in data.get("categories", [])]
    except (json.JSONDecodeError, FileNotFoundError):
        return []

def save_event_categories(categories: List[EventCategory]):
    """Save event categories to JSON file"""
    os.makedirs(os.path.dirname(EVENT_CATEGORIES_PATH), exist_ok=True)
    data = {
        "categories": [cat.to_dict() for cat in categories]
    }
    with open(EVENT_CATEGORIES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def add_event_category(name: str, description: str = "", is_event: bool = False) -> str:
    """Add a new event category"""
    categories = load_event_categories()
    
    # Generate unique ID
    category_id = f"cat_{len(categories)}_{int(datetime.now().timestamp())}"
    
    new_category = EventCategory(category_id, name, description, is_event=is_event)
    categories.append(new_category)
    save_event_categories(categories)
    return category_id

def remove_event_category(category_id: str) -> bool:
    """Remove an event category"""
    categories = load_event_categories()
    remaining_categories = [cat for cat in categories if cat.id != category_id]
    
    if len(remaining_categories) < len(categories):
        save_event_categories(remaining_categories)
        return True
    return False

def get_category_by_id(category_id: str) -> Optional[EventCategory]:
    """Get a category by its ID"""
    categories = load_event_categories()
    for cat in categories:
        if cat.id == category_id:
            return cat
    return None

def get_category_names() -> Dict[str, str]:
    """Get a dictionary of category IDs to names"""
    categories = load_event_categories()
    return {cat.id: cat.name for cat in categories}