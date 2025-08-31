import requests
import json
from datetime import datetime
from typing import Dict, List, Optional
from app.config.knowledge_config import get_active_knowledge_bases
from app.models.event_category import load_event_categories, get_category_names

# Dynamic event sources from knowledge bases - no hardcoded defaults
EVENT_SOURCES: Dict[str, List[Dict]] = {}

def get_event_sources_from_knowledge_bases():
    """Load event sources from knowledge bases configuration"""
    global EVENT_SOURCES
    EVENT_SOURCES = {}
    
    knowledge_bases = get_active_knowledge_bases()
    for kb in knowledge_bases:
        if kb.get('is_events', False) and kb.get('event_category') and kb.get('source'):
            category = kb['event_category']
            if category not in EVENT_SOURCES:
                EVENT_SOURCES[category] = []
            
            EVENT_SOURCES[category].append({
                'url': kb['source'],
                'title': kb['title'],
                'kb_id': kb['id']
            })

def add_event_source(url: str, category: str, title: str = "", kb_id: str = ""):
    """Add a new event source URL for a category"""
    if category not in EVENT_SOURCES:
        EVENT_SOURCES[category] = []
    
    # Check if URL already exists in this category
    for source in EVENT_SOURCES[category]:
        if source['url'] == url:
            return False
    
    EVENT_SOURCES[category].append({
        'url': url,
        'title': title,
        'kb_id': kb_id
    })
    return True

def remove_event_source(url: str, category: Optional[str] = None):
    """Remove an event source URL"""
    if category:
        if category in EVENT_SOURCES:
            EVENT_SOURCES[category] = [source for source in EVENT_SOURCES[category] if source['url'] != url]
            return True
    else:
        for cat in EVENT_SOURCES:
            EVENT_SOURCES[cat] = [source for source in EVENT_SOURCES[cat] if source['url'] != url]
        return True
    return False

def fetch_event_data():
    """Fetch event data from all configured knowledge base sources"""
    # Refresh event sources from knowledge bases
    get_event_sources_from_knowledge_bases()
    
    events = {}
    
    # Helper function to fetch and parse JSON from a URL
    def fetch_json(url, source_info):
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            # Handle both array and object responses
            events_data = data if isinstance(data, list) else [data]
            # Add source information to each event
            for event in events_data:
                event['_source'] = source_info['title']
                event['_kb_id'] = source_info['kb_id']
            return events_data
        except Exception as e:
            print(f"❌ Failed to fetch events from {url} ({source_info['title']}): {e}")
            return []
    
    # Fetch from knowledge base sources only - no hardcoded defaults
    for category in EVENT_SOURCES:
        if category not in events:
            events[category] = []
        
        for source in EVENT_SOURCES[category]:
            events[category].extend(fetch_json(source['url'], source))
    
    return events

def fetch_agent_event_data(agent_kb_ids):
    """Fetch event data only from knowledge bases accessible to the agent"""
    from app.config.knowledge_config import get_knowledge_bases_for_agent
    
    # Get only the knowledge bases the agent has access to
    agent_knowledge_bases = []
    all_kbs = get_active_knowledge_bases()
    for kb in all_kbs:
        if kb['id'] in agent_kb_ids and kb.get('is_events', False):
            agent_knowledge_bases.append(kb)
    
    events = {}
    
    # Helper function to fetch and parse JSON from a URL
    def fetch_json(url, source_info):
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            # Handle both array and object responses
            events_data = data if isinstance(data, list) else [data]
            # Add source information to each event
            for event in events_data:
                event['_source'] = source_info['title']
                event['_kb_id'] = source_info['kb_id']
            return events_data
        except Exception as e:
            print(f"❌ Failed to fetch events from {url} ({source_info['title']}): {e}")
            return []
    
    # Fetch only from agent-accessible knowledge bases
    for kb in agent_knowledge_bases:
        if kb.get('event_category') and kb.get('source'):
            category = kb['event_category']
            if category not in events:
                events[category] = []
            
            source_info = {
                'url': kb['source'],
                'title': kb['title'],
                'kb_id': kb['id']
            }
            events[category].extend(fetch_json(kb['source'], source_info))
    
    return events

def format_event_entry(entry):
    """Format an event entry for display in the requested format"""
    # Try to get location from various possible fields
    location = entry.get('Location') or entry.get('location') or entry.get('venue') or 'Unknown'
    
    # Try to get date information
    start_date = (entry.get('StartDate') or entry.get('start_date') or 
                 entry.get('Date') or entry.get('date') or 'N/A')
    end_date = (entry.get('EndDate') or entry.get('end_date') or 
                entry.get('completion_date') or None)
    
    # Try to get time information and parse it
    time_raw = entry.get('Time') or entry.get('time') or entry.get('schedule', {})
    if isinstance(time_raw, str):
        # If it's already a string like "9am - 1:30pm", use it directly
        time_str = time_raw
    elif isinstance(time_raw, dict):
        # If it's a dict with start/end times
        start_time = time_raw.get('start') or time_raw.get('start_time', 'N/A')
        end_time = time_raw.get('end') or time_raw.get('end_time', 'N/A')
        time_str = f"{start_time} - {end_time}"
    else:
        time_str = 'N/A'
    
    # Try to get days information
    days_info = (entry.get('Days') or entry.get('days') or 
                entry.get('schedule_days') or 'N/A')
    
    # Get source information for reference
    source = entry.get('_source', 'Unknown Source')
    
    # Format the entry in the requested format
    formatted_entry = f"📌 {location}\n"
    formatted_entry += f"📆 {start_date}"
    if end_date and end_date != start_date:
        formatted_entry += f" – {end_date}"
    formatted_entry += f"\n📋 {days_info}\n"
    formatted_entry += f"⏱️ {time_str}"
    
    return formatted_entry


def get_upcoming_events(category: str = "classes", limit=3):
    """Get upcoming events for a specific category"""
    events = fetch_event_data()
    category_events = events.get(category, [])
    
    def parse_date(entry):
        # Try multiple date field formats
        date_fields = ['start_date', 'StartDate', 'date', 'Date']
        for field in date_fields:
            if field in entry:
                date_str = entry[field]
                # Try multiple date formats
                date_formats = [
                    "%Y-%m-%d",      # 2025-08-09
                    "%m/%d/%Y",      # 08/09/2025
                    "%b %d, %Y",     # Aug 9, 2025
                    "%B %d, %Y",     # August 9, 2025
                    "%b %d %Y",      # Aug 9 2025
                    "%B %d %Y"       # August 9 2025
                ]
                
                for fmt in date_formats:
                    try:
                        return datetime.strptime(date_str, fmt)
                    except ValueError:
                        continue
        return datetime.max

    sorted_events = sorted(category_events, key=parse_date)
    return [format_event_entry(e) for e in sorted_events[:limit]]

def get_upcoming_events_grouped_by_location(category: str = "classes", limit=10, agent_kb_ids=None):
    """Get upcoming events grouped by location with the requested format"""
    if agent_kb_ids is not None:
        # Use agent-specific event data
        events = fetch_agent_event_data(agent_kb_ids)
    else:
        # Use all event data (fallback)
        events = fetch_event_data()
    category_events = events.get(category, [])
    
    def parse_date(entry):
        # Try multiple date field formats
        date_fields = ['start_date', 'StartDate', 'date', 'Date']
        for field in date_fields:
            if field in entry:
                date_str = entry[field]
                # Try multiple date formats
                date_formats = [
                    "%Y-%m-%d",      # 2025-08-09
                    "%m/%d/%Y",      # 08/09/2025
                    "%b %d, %Y",     # Aug 9, 2025
                    "%B %d, %Y",     # August 9, 2025
                    "%b %d %Y",      # Aug 9 2025
                    "%B %d %Y"       # August 9 2025
                ]
                
                for fmt in date_formats:
                    try:
                        return datetime.strptime(date_str, fmt)
                    except ValueError:
                        continue
        return datetime.max

    # Sort events by date
    sorted_events = sorted(category_events, key=parse_date)
    
    # Group events by location
    location_groups = {}
    for event in sorted_events[:limit]:
        location = event.get('Location') or event.get('location') or event.get('venue') or 'Unknown'
        if location not in location_groups:
            location_groups[location] = []
        location_groups[location].append(event)
    
    # Format each location group
    formatted_groups = []
    for location, events in location_groups.items():
        group_text = f"📌 {location}\n"
        
        for event in events:
            # Get date information
            start_date = (event.get('StartDate') or event.get('start_date') or 
                         event.get('Date') or event.get('date') or 'N/A')
            end_date = (event.get('EndDate') or event.get('end_date') or 
                        event.get('completion_date') or None)
            
            # Get time information - try multiple time field formats
            time_str = 'N/A'
            if event.get('Time'):
                time_str = event.get('Time')
            elif event.get('StartTime') and event.get('EndTime'):
                start_time = event.get('StartTime')
                end_time = event.get('EndTime')
                time_str = f"{start_time} - {end_time}"
            elif event.get('time'):
                time_str = event.get('time')
            elif event.get('schedule'):
                schedule = event.get('schedule')
                if isinstance(schedule, dict):
                    start_time = schedule.get('start') or schedule.get('start_time', 'N/A')
                    end_time = schedule.get('end') or schedule.get('end_time', 'N/A')
                    time_str = f"{start_time} - {end_time}"
                elif isinstance(schedule, str):
                    time_str = schedule
            
            # Get days information
            days_info = (event.get('Days') or event.get('days') or 
                        event.get('schedule_days') or 'N/A')
            
            # Format the event entry
            group_text += f"📆 {start_date}"
            if end_date and end_date != start_date:
                group_text += f" – {end_date}"
            group_text += f"\n📋 {days_info}\n"
            group_text += f"⏱️ {time_str}\n"
        
        formatted_groups.append(group_text)
    
    return formatted_groups

def get_available_categories():
    """Get all available event categories from knowledge bases"""
    get_event_sources_from_knowledge_bases()
    return list(EVENT_SOURCES.keys())

# Backward compatibility function
def get_upcoming_classes(location: str = "classes", limit=3):
    """Backward compatibility - now maps to get_upcoming_events"""
    return get_upcoming_events(location, limit)

# Backward compatibility function
def format_class_entry(entry):
    """Backward compatibility - now maps to format_event_entry"""
    return format_event_entry(entry)

# Debug / demo
if __name__ == "__main__":
    categories = get_available_categories()
    print(f"Available categories: {categories}")
    
    for category in categories:
        print(f"\n🔍 {category.title()} events:")
        for line in get_upcoming_events(category):
            print(line)
            print("–––")
