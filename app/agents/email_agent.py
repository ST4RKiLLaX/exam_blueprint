import os
import numpy as np
from openai import OpenAI
from dotenv import load_dotenv
from app.utils.event_parser import get_upcoming_events, get_upcoming_events_grouped_by_location, get_available_categories, fetch_event_data
# Default configuration for fallback when no agent is specified
DEFAULT_CONFIG = {
    "personality": "You are a helpful AI assistant.",
    "style": "Use a professional and friendly tone.",
    "prompt": "Please provide helpful and accurate responses."
}
from app.config.knowledge_config import get_active_knowledge_bases, get_knowledge_bases_for_agent
from app.utils.knowledge_processor import search_knowledge_base
from app.config.model_config import get_current_model, get_current_temperature


load_dotenv()

# Initialize OpenAI client with API key from config or environment
def _get_openai_client():
    """Get OpenAI client with proper API key"""
    try:
        from app.config.api_config import get_openai_api_key
        api_key = get_openai_api_key()
        if not api_key:
            # Fallback to environment variable
            api_key = os.getenv("OPENAI_API_KEY")
        return OpenAI(api_key=api_key)
    except ImportError:
        # Fallback if api_config is not available
        return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

client = _get_openai_client()

def embed_query(text):
    response = client.embeddings.create(
        input=text,
        model="text-embedding-3-small"
    )
    return np.array(response.data[0].embedding, dtype="float32")

def search_all_knowledge_bases(query, top_k=3, agent=None):
    """Search across all active knowledge bases (legacy function for backward compatibility)"""
    all_results = []
    
    if agent:
        # Use agent-specific knowledge bases
        knowledge_bases = get_knowledge_bases_for_agent(agent.agent_id, agent.knowledge_bases)
    else:
        # Fallback to all active knowledge bases
        knowledge_bases = get_active_knowledge_bases()
    
    for kb in knowledge_bases:
        kb_results = search_knowledge_base(kb["id"], query, top_k)
        if kb_results:
            all_results.extend(kb_results)
    
    return all_results

def search_agent_knowledge_bases(query, agent, top_k=3):
    """Search across knowledge bases that the agent has access to"""
    all_results = []
    
    # Get knowledge bases accessible to this agent
    knowledge_bases = get_knowledge_bases_for_agent(agent.agent_id, agent.knowledge_bases)
    
    for kb in knowledge_bases:
        kb_results = search_knowledge_base(kb["id"], query, top_k)
        if kb_results:
            all_results.extend(kb_results)
    
    return all_results

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

def build_prompt(email_body, history=None, agent=None):
    # Use agent-specific prompt or fallback to default config
    if agent:
        agent_prompt = agent.prompt or DEFAULT_CONFIG.get("prompt", "")
        # Search agent-specific knowledge bases
        knowledge_refs = search_agent_knowledge_bases(email_body, agent)
    else:
        agent_prompt = DEFAULT_CONFIG.get("prompt", "")
        # Fallback to all knowledge bases
        knowledge_refs = search_all_knowledge_bases(email_body)
    
    # Get events from all categories
    all_events = []
    categories = get_available_categories()
    
    if categories:
        all_events.append("\nAVAILABLE SCHEDULES:")
        for category in categories:
            events = get_upcoming_events_grouped_by_location(category, limit=10)
            if events:
                all_events.append(f"\n=== {category.upper()} ===")
                all_events.extend(events)
                all_events.append("")  # Add blank line between categories
    else:
        all_events.append("No event schedules available at this time.")
    
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
{context}

Reply:
"""

def generate_reply(email_body, history=None, agent=None):
    # Use agent-specific personality and style or fallback to default config
    if agent:
        personality = agent.personality or DEFAULT_CONFIG["personality"]
        style = agent.style or DEFAULT_CONFIG["style"]
    else:
        personality = DEFAULT_CONFIG["personality"]
        style = DEFAULT_CONFIG["style"]

    prompt = build_prompt(email_body, history=history, agent=agent)
    
    # Get current model configuration
    current_model = get_current_model()
    current_temp = get_current_temperature()
    
    # GPT-5 only supports default temperature (1.0)
    if current_model == "gpt-5":
        response = client.chat.completions.create(
            model=current_model,
            messages=[
                {"role": "system", "content": personality + "\n" + style},
                {"role": "user", "content": prompt}
            ]
        )
    else:
        response = client.chat.completions.create(
            model=current_model,
            messages=[
                {"role": "system", "content": personality + "\n" + style},
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
