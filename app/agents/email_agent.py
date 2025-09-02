import os
import numpy as np
from openai import OpenAI
from dotenv import load_dotenv
from app.utils.event_parser import get_upcoming_events, get_upcoming_events_grouped_by_location, get_available_categories, fetch_event_data, get_event_sources_from_knowledge_bases
# Default configuration for fallback when no agent is specified
DEFAULT_CONFIG = {
    "personality": "You are a helpful AI assistant.",
    "style": "Use a professional and friendly tone.",
    "prompt": "Please provide helpful and accurate responses."
}
from app.config.knowledge_config import get_active_knowledge_bases, get_knowledge_bases_for_agent
from app.utils.knowledge_processor import search_knowledge_base
from app.config.model_config import get_current_model, get_current_temperature
from app.utils.secure_access import secure_knowledge_base_access


load_dotenv()

# Initialize OpenAI client with API key from config
def _get_openai_client():
    """Get OpenAI client with proper API key"""
    try:
        from app.config.api_config import get_openai_api_key
        api_key = get_openai_api_key()
        if not api_key:
            raise ValueError("No API key configured")
        return OpenAI(api_key=api_key)
    except ImportError:
        raise ValueError("API config not available")

# Don't create client at import time - create when needed

def embed_query(text):
    response = _get_openai_client().embeddings.create(
        input=text,
        model="text-embedding-3-small"
    )
    return np.array(response.data[0].embedding, dtype="float32")

def search_all_knowledge_bases(query, top_k=3, agent=None):
    """
    SECURE SEARCH: Implicit deny - agents can ONLY access their assigned knowledge bases.
    No fallbacks, no bypasses, no exceptions.
    """
    if not agent:
        print("🚫 SECURITY: No agent specified - denying all knowledge base access")
        return []
    
    if not agent.knowledge_bases:
        print(f"🚫 SECURITY: Agent '{agent.name}' has no assigned knowledge bases - denying all access")
        return []
    
    # STRICT: Only agent-assigned knowledge bases
    knowledge_bases = get_knowledge_bases_for_agent(agent.agent_id, agent.knowledge_bases)
    
    all_results = []
    for kb in knowledge_bases:
        kb_results = search_knowledge_base(kb["id"], query, top_k)
        if kb_results:
            all_results.extend(kb_results)
    
    return all_results

def search_agent_knowledge_bases(query, agent, top_k=3):
    """
    SECURE SEARCH: Implicit deny - agents can ONLY access their assigned knowledge bases.
    """
    if not agent:
        print("🚫 SECURITY: No agent specified - denying all knowledge base access")
        return []
    
    if not agent.knowledge_bases:
        print(f"🚫 SECURITY: Agent '{agent.name}' has no assigned knowledge bases - denying all access")
        return []
    
    # STRICT: Only agent-assigned knowledge bases
    knowledge_bases = get_knowledge_bases_for_agent(agent.agent_id, agent.knowledge_bases)
    
    all_results = []
    for kb in knowledge_bases:
        kb_results = search_knowledge_base(kb["id"], query, top_k)
        if kb_results:
            all_results.extend(kb_results)
    
    return all_results

def search_location_filtered_knowledge_bases(query, agent, filtered_kb_ids, top_k=3):
    """
    SECURE SEARCH: Implicit deny - agents can ONLY access their assigned knowledge bases.
    Location filtering only applies within authorized KBs.
    """
    if not agent:
        print("🚫 SECURITY: No agent specified - denying all knowledge base access")
        return []
    
    if not agent.knowledge_bases:
        print(f"🚫 SECURITY: Agent '{agent.name}' has no assigned knowledge bases - denying all access")
        return []
    
    # Validate that all requested KB IDs are authorized for this agent
    unauthorized_kbs = [kb_id for kb_id in filtered_kb_ids if kb_id not in agent.knowledge_bases]
    if unauthorized_kbs:
        print(f"🚫 SECURITY: Agent '{agent.name}' attempted to access unauthorized KBs: {unauthorized_kbs}")
        print(f"   Authorized KBs: {agent.knowledge_bases}")
        # Filter to only authorized KBs
        filtered_kb_ids = [kb_id for kb_id in filtered_kb_ids if kb_id in agent.knowledge_bases]
    
    # Get knowledge bases accessible to this agent, filtered by location
    knowledge_bases = get_knowledge_bases_for_agent(agent.agent_id, filtered_kb_ids)
    
    all_results = []
    for kb in knowledge_bases:
        kb_results = search_knowledge_base(kb["id"], query, top_k)
        if kb_results:
            all_results.extend(kb_results)
    
    return all_results

def get_agent_event_categories(agent):
    """
    SECURE ACCESS: Implicit deny - agents can ONLY access event categories from their assigned knowledge bases.
    """
    if not agent:
        print("🚫 SECURITY: No agent specified - denying all event category access")
        return []
    
    if not agent.knowledge_bases:
        print(f"🚫 SECURITY: Agent '{agent.name}' has no assigned knowledge bases - denying all event category access")
        return []
    
    # STRICT: Only knowledge bases assigned to the agent
    accessible_kbs = secure_knowledge_base_access(agent)
    
    # Extract event categories from accessible knowledge bases
    agent_categories = []
    for kb in accessible_kbs:
        if kb.get('is_events', False) and kb.get('event_category'):
            category = kb['event_category']
            if category not in agent_categories:
                agent_categories.append(category)
    
    print(f"🔒 SECURITY: Agent '{agent.name}' accessing event categories: {agent_categories}")
    return agent_categories

def detect_location(email_body):
    """
    Detect the student's location from the email content.
    Returns 'Long Island', 'New York City', or 'New York City' as default.
    Uses comprehensive location data from knowledge base descriptions.
    """
    email_lower = email_body.lower()
    
    # Long Island areas (from KB description)
    long_island_keywords = [
        'long island', 'li', 'nassau', 'suffolk', 'mineola', 'west hempstead', 
        'franklin square', 'uniondale', 'new hyde park', 'westbury', 
        'north new hyde park', 'floral park', 'hempstead', 'garden city south', 
        'garden city park', 'east garden city', 'williston park', 'east williston', 
        'carle place', 'stewart manor', 'herricks', 'hillside manor', 'baldwin', 
        'north merrick', 'elmont', 'garden city', 'levittown', 'hicksville', 
        'freeport', 'babylon', 'huntington', 'islip', 'oyster bay', 'brookhaven', 
        'smithtown'
    ]
    
    # NYC/Manhattan areas (from KB description + Brooklyn proximity)
    nyc_keywords = [
        'manhattan', 'the bronx', 'brooklyn', 'queens', 'staten island', 
        'jersey city', 'hoboken', 'weehawken', 'union city', 'west new york', 
        'fort lee', 'edgewater', 'long island city', 'astoria', 'harlem', 
        'williamsburg', 'greenpoint', 'bushwick', 'park slope', 'flushing', 
        'forest hills', 'jackson heights', 'bay ridge', 'sunnyside', 
        'upper east side', 'upper west side', 'midtown', 'soho', 'tribeca', 
        'chinatown', 'lower east side', 'east village', 'greenwich village',
        'nyc', 'new york city', 'times square', 'broadway', 'herald square', 
        'penn station', 'grand central', 'chelsea', 'hell\'s kitchen', 
        'garment district', 'dumbo', 'brooklyn heights', 'bk'
    ]
    
    # Check for Long Island indicators first
    for keyword in long_island_keywords:
        if keyword in email_lower:
            return 'Long Island'
    
    # Check for NYC indicators (includes Brooklyn → Manhattan proximity)
    for keyword in nyc_keywords:
        if keyword in email_lower:
            return 'New York City'
    
    # Default to NYC if no location indicators found
    return 'New York City'

def filter_knowledge_bases_by_location(agent_kb_ids, detected_location):
    """Filter knowledge bases based on detected location using KB descriptions"""
    try:
        from app.config.knowledge_config import load_knowledge_config
        
        if not agent_kb_ids or not detected_location:
            return agent_kb_ids
        
        config = load_knowledge_config()
        filtered_kb_ids = []
        
        print(f"🔍 Filtering KBs for detected location: {detected_location}")
        
        for kb_id in agent_kb_ids:
            # Find the knowledge base
            kb_info = None
            for kb in config.get('knowledge_bases', []):
                if kb.get('id') == kb_id:
                    kb_info = kb
                    break
            
            if not kb_info:
                continue
            
            # Only filter event knowledge bases
            if not kb_info.get('is_events', False):
                filtered_kb_ids.append(kb_id)  # Include non-event KBs
                continue
            
            kb_description = kb_info.get('description', '').lower()
            kb_title = kb_info.get('title', '').lower()
            
            # Check if the detected location matches this KB's coverage area
            location_match = False
            
            if detected_location == 'Long Island':
                # Look for Long Island indicators in KB description/title
                li_indicators = [
                    'long island', 'garden city', 'mineola', 'westbury', 'hempstead',
                    'uniondale', 'nassau', 'suffolk', 'carle place', 'new hyde park',
                    'floral park', 'franklin square', 'west hempstead'
                ]
                
                for indicator in li_indicators:
                    if indicator in kb_description or indicator in kb_title:
                        location_match = True
                        break
                        
            elif detected_location == 'New York City':
                # Look for NYC indicators in KB description/title
                nyc_indicators = [
                    'new york city', 'manhattan', 'brooklyn', 'queens', 'bronx',
                    'staten island', 'nyc', 'jersey city', 'hoboken', 'midtown'
                ]
                
                for indicator in nyc_indicators:
                    if indicator in kb_description or indicator in kb_title:
                        location_match = True
                        break
            
            if location_match:
                filtered_kb_ids.append(kb_id)
                print(f"✅ Including KB: {kb_info.get('title')} (matches {detected_location})")
            else:
                print(f"❌ Excluding KB: {kb_info.get('title')} (doesn't match {detected_location})")
        
        print(f"📋 Filtered {len(agent_kb_ids)} → {len(filtered_kb_ids)} knowledge bases")
        return filtered_kb_ids
        
    except Exception as e:
        print(f"Error filtering knowledge bases by location: {e}")
        return agent_kb_ids  # Return original list on error

def build_prompt(email_body, history=None, agent=None):
    # SECURITY: Require agent for knowledge base access
    if not agent:
        print("🚫 SECURITY: No agent specified - denying all knowledge base access")
        knowledge_refs = []
        all_events = []
        agent_prompt = DEFAULT_CONFIG.get("prompt", "")
        categories = []
        location_filtered_kb_ids = None
    else:
        agent_prompt = agent.prompt or DEFAULT_CONFIG.get("prompt", "")
        
        # Detect location first to filter knowledge bases
        detected_location = detect_location(email_body)
        location_filtered_kb_ids = filter_knowledge_bases_by_location(agent.knowledge_bases, detected_location)
        
        # Search only location-filtered knowledge bases
        knowledge_refs = search_location_filtered_knowledge_bases(email_body, agent, location_filtered_kb_ids)
        
        # Get events based on agent permissions AND detected location
        all_events = []
        # Use the already detected location and filtered KB IDs
        # Get only categories that the agent has access to
        categories = get_agent_event_categories(agent)
    
    if categories:
        all_events.append("\nAVAILABLE SCHEDULES:")
        for category in categories:
            # Use location-filtered knowledge base IDs for events
            events = get_upcoming_events_grouped_by_location(category, limit=10, agent_kb_ids=location_filtered_kb_ids)
            if events:
                all_events.append(f"\n=== {category.upper()} ===")
                all_events.extend(events)
                all_events.append("")  # Add blank line between categories
    else:
        if agent:
            all_events.append("No event schedules available for this agent.")
        else:
            all_events.append("No event schedules available at this time.")
    
    # Add agent identity context
    agent_identity = ""
    if agent:
        agent_identity = f"\nAGENT IDENTITY:\n---\nYou are {agent.name}, an AI assistant.\n"
    
    context = "\n".join([
        "KNOWLEDGE BASE INFORMATION:",
        "---",
        *knowledge_refs,
        "\nSCHEDULE INFORMATION:",
        "---",
        *all_events,
        "\nAGENT INSTRUCTIONS:",
        "---",
        agent_prompt
    ])
    
    # Add formatting rules if specified
    formatting_rules = ""
    if agent and agent.formatting:
        formatting_rules = f"\nFORMATTING RULES:\n---\n{agent.formatting}\n"
    
    convo = ""
    if history:
        lines = []
        for m in history[-10:]:
            role = "User" if m.get("role") == "user" else "Assistant"
            content = m.get("content", "")
            lines.append(f"{role}: {content}")
        if lines:
            convo = "Conversation so far:\n" + "\n".join(lines) + "\n\n"

    return f"""
You are a helpful AI assistant.
Answer the following email using the context below. 

CRITICAL RULES:
1. When discussing schedules, you MUST use the EXACT format provided in the schedule information. 
2. Do NOT create your own formatting, numbering, or structure. 
3. Copy the schedule information exactly as it appears with all icons (📌, 📆, 📋, ⏱️) and formatting.
4. NEVER use markdown link format [text](url). Always provide URLs directly in plain text format.

    {convo}Email:
\"\"\"
{email_body}
\"\"\"

Context:
{agent_identity}{context}{formatting_rules}

Reply:
"""

def generate_reply(email_body, history=None, agent=None):
    # SECURITY: Require agent for all operations
    if not agent:
        print("🚫 SECURITY: No agent specified - denying reply generation")
        return "🚫 ACCESS DENIED: No agent specified. Please select an agent to generate a reply."
    
    # Use agent-specific personality and style
    personality = agent.personality or DEFAULT_CONFIG["personality"]
    style = agent.style or DEFAULT_CONFIG["style"]
    
    # Automatically inject agent identity into the system message
    agent_identity = f"You are {agent.name}, an AI assistant. "
    system_message = agent_identity + personality + "\n" + style

    prompt = build_prompt(email_body, history=history, agent=agent)
    
    # SECURITY: If no knowledge base access was granted, block the reply
    if not agent and "KNOWLEDGE BASE INFORMATION:" in prompt and "---" in prompt:
        kb_content = prompt.split("KNOWLEDGE BASE INFORMATION:")[1].split("SCHEDULE INFORMATION:")[0]
        if kb_content.strip() == "---":
            print("🚫 SECURITY: No knowledge base access - blocking reply generation")
            return "🚫 ACCESS DENIED: No knowledge base access granted. Please select an agent with proper permissions."
    
    # Get current model configuration
    current_model = get_current_model()
    current_temp = get_current_temperature()
    
    # GPT-5 only supports default temperature (1.0)
    if current_model == "gpt-5":
        response = _get_openai_client().chat.completions.create(
            model=current_model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ]
        )
    else:
        response = _get_openai_client().chat.completions.create(
            model=current_model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            temperature=current_temp
        )
    return response.choices[0].message.content.strip()


# Manual test
if __name__ == "__main__":
    sample_email = """Hi, I'm interested in your services. I live in Long Island.
I don’t have a high school diploma—am I still eligible?
Also how long is the program?"""
    
    reply = generate_reply(sample_email)
    print("📩 Suggested reply:\n")
    print(reply)
