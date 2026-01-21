# Knowledge Base Configuration
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any

KNOWLEDGE_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "knowledge_bases.json")

# Default knowledge bases structure - no hardcoded defaults
DEFAULT_KNOWLEDGE_BASES = {
    "knowledge_bases": []
}

def load_knowledge_config():
    """Load knowledge bases configuration from JSON file"""
    if not os.path.exists(KNOWLEDGE_CONFIG_PATH):
        save_knowledge_config(DEFAULT_KNOWLEDGE_BASES)
        return DEFAULT_KNOWLEDGE_BASES
    
    try:
        with open(KNOWLEDGE_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return DEFAULT_KNOWLEDGE_BASES

def save_knowledge_config(config):
    """Save knowledge bases configuration to JSON file"""
    with open(KNOWLEDGE_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def update_embedding_status(kb_id, status):
    """Update the embedding status of a knowledge base"""
    config = load_knowledge_config()
    for kb in config["knowledge_bases"]:
        if kb["id"] == kb_id:
            kb["embedding_status"] = status
            save_knowledge_config(config)
            return True
    return False

def add_knowledge_base(title, description, kb_type, source, chunks_path=None, is_events=False, access_type="shared", category="general", refresh_schedule="manual", cissp_type=None, cissp_domain=None, embedding_provider="openai", embedding_model=None):
    """Add a new knowledge base to the configuration"""
    config = load_knowledge_config()
    
    # Generate unique ID
    kb_id = f"kb_{len(config['knowledge_bases'])}_{int(datetime.now().timestamp())}"
    
    new_kb = {
        "id": kb_id,
        "title": title,
        "description": description,
        "type": kb_type,
        "source": source,
        "chunks_path": chunks_path,
        "created_at": datetime.now().isoformat(),
        "status": "active",
        "is_events": is_events,
        "access_type": access_type,  # "shared" or "exclusive"
        "category": category,  # "general", "cna", "pharmacy", "admin", etc.
        "refresh_schedule": refresh_schedule,  # "manual", "hourly", "daily", "weekly", "on_use"
        "last_refreshed": datetime.now().isoformat() if kb_type == "url" else None,
        "next_refresh": None,  # Will be calculated based on schedule
        "cissp_type": cissp_type,  # "outline", "cbk", or None
        "cissp_domain": cissp_domain,  # domain name string or None
        "embedding_provider": embedding_provider,  # "openai", "gemini", etc.
        "embedding_model": embedding_model  # specific embedding model or None for provider default
    }
    
    config["knowledge_bases"].append(new_kb)
    save_knowledge_config(config)
    return kb_id

def remove_knowledge_base(kb_id):
    """Remove a knowledge base from the configuration and clean up associated files"""
    import shutil
    
    config = load_knowledge_config()
    
    # Find the knowledge base to be removed
    kb_to_remove = None
    remaining_kbs = []
    
    for kb in config["knowledge_bases"]:
        if kb["id"] == kb_id:
            kb_to_remove = kb
        else:
            remaining_kbs.append(kb)
    
    if kb_to_remove:
        # Clean up files based on knowledge base type
        if kb_to_remove["type"] == "file":
            # Remove the original uploaded file
            try:
                if os.path.exists(kb_to_remove["source"]):
                    os.remove(kb_to_remove["source"])
                    print(f"Removed source file: {kb_to_remove['source']}")
            except Exception as e:
                print(f"Error removing source file: {e}")
        
        # Remove the knowledge base folder with embeddings (for all types except embedded)
        if kb_to_remove["type"] != "embedded":
            kb_folder = os.path.join(os.path.dirname(__file__), "..", "knowledge_bases", kb_id)
            if os.path.exists(kb_folder):
                try:
                    shutil.rmtree(kb_folder)
                    print(f"Removed knowledge base folder: {kb_folder}")
                except Exception as e:
                    print(f"Error removing knowledge base folder: {e}")
            else:
                print(f"Knowledge base folder not found (already cleaned): {kb_folder}")
        
        # Update configuration
        config["knowledge_bases"] = remaining_kbs
        save_knowledge_config(config)
        
        # Clean up agent references to this knowledge base
        _cleanup_agent_kb_references(kb_id)
        
        print(f"Removed knowledge base: {kb_to_remove['title']} ({kb_id})")
        return True
    
    return False

def _cleanup_agent_kb_references(kb_id):
    """Remove references to deleted knowledge base from all agents"""
    try:
        from app.models.agent import agent_manager
        
        # Get all agents and check if they reference the deleted KB
        agents_updated = 0
        for agent in agent_manager.get_all_agents():
            if kb_id in agent.knowledge_bases:
                # Remove the KB reference from the agent
                agent.knowledge_bases.remove(kb_id)
                agents_updated += 1
        
        # Save the updated agents if any were modified
        if agents_updated > 0:
            agent_manager.save_agents()
            print(f"Cleaned up knowledge base references from {agents_updated} agents")
            
    except Exception as e:
        print(f"Error cleaning up agent KB references: {e}")

def get_active_knowledge_bases():
    """Get all active knowledge bases"""
    config = load_knowledge_config()
    return [kb for kb in config["knowledge_bases"] if kb["status"] == "active"]

def get_knowledge_bases_for_agent(agent_id: str, agent_knowledge_bases: list = None):
    """Get knowledge bases that an agent has access to.
    
    Args:
        agent_id: The ID of the agent
        agent_knowledge_bases: List of knowledge base IDs explicitly assigned to the agent
        
    Returns:
        List of knowledge base configurations that the agent can access.
        Only returns knowledge bases that are explicitly assigned to the agent.
    """
    config = load_knowledge_config()
    all_kbs = [kb for kb in config.get("knowledge_bases", []) if kb.get("status") == "active"]
    
    # If no agent knowledge bases specified, return empty list (no access)
    if not agent_knowledge_bases:
        return []
    
    accessible_kbs = []
    for kb in all_kbs:
        # Only include knowledge bases that are explicitly assigned to the agent
        if kb["id"] in agent_knowledge_bases:
            accessible_kbs.append(kb)
    
    return accessible_kbs

def cleanup_orphaned_kb_references():
    """Clean up any orphaned knowledge base references from agents"""
    try:
        from app.models.agent import agent_manager
        
        # Get all valid KB IDs
        config = load_knowledge_config()
        valid_kb_ids = {kb["id"] for kb in config.get("knowledge_bases", [])}
        
        agents_updated = 0
        total_orphans_removed = 0
        
        for agent in agent_manager.get_all_agents():
            original_kb_count = len(agent.knowledge_bases)
            # Filter out any KB IDs that no longer exist
            agent.knowledge_bases = [kb_id for kb_id in agent.knowledge_bases if kb_id in valid_kb_ids]
            
            orphans_removed = original_kb_count - len(agent.knowledge_bases)
            if orphans_removed > 0:
                agents_updated += 1
                total_orphans_removed += orphans_removed
        
        # Save the updated agents if any were modified
        if agents_updated > 0:
            agent_manager.save_agents()
            print(f"Cleaned up {total_orphans_removed} orphaned KB references from {agents_updated} agents")
            return True
        
        return False
        
    except Exception as e:
        print(f"Error cleaning up orphaned KB references: {e}")
        return False

def cleanup_orphaned_kb_folders():
    """Clean up knowledge base folders that exist in filesystem but not in configuration"""
    import shutil
    
    try:
        # Get all valid KB IDs from the configuration
        config = load_knowledge_config()
        valid_kb_ids = set(kb["id"] for kb in config.get("knowledge_bases", []))
        
        # Check knowledge_bases directory for orphaned folders
        kb_base_dir = os.path.join(os.path.dirname(__file__), "..", "knowledge_bases")
        if os.path.exists(kb_base_dir):
            cleaned_count = 0
            for item in os.listdir(kb_base_dir):
                item_path = os.path.join(kb_base_dir, item)
                
                # Check if it's a directory that looks like a KB ID (starts with "kb_")
                if os.path.isdir(item_path) and item.startswith("kb_") and item not in valid_kb_ids:
                    try:
                        shutil.rmtree(item_path)
                        print(f"Removed orphaned knowledge base folder: {item}")
                        cleaned_count += 1
                    except Exception as e:
                        print(f"Error removing orphaned folder {item}: {e}")
            
            if cleaned_count > 0:
                print(f"Cleaned up {cleaned_count} orphaned knowledge base folders")
                return True
            else:
                print("No orphaned knowledge base folders found")
                return False
                
    except Exception as e:
        print(f"Error cleaning up orphaned KB folders: {e}")
        return False

def full_knowledge_base_cleanup():
    """Perform complete cleanup of orphaned knowledge base data"""
    print("Starting comprehensive knowledge base cleanup...")
    refs_cleaned = cleanup_orphaned_kb_references()
    folders_cleaned = cleanup_orphaned_kb_folders()
    
    if refs_cleaned or folders_cleaned:
        print("Knowledge base cleanup completed - orphaned data removed!")
        return True
    else:
        print("Knowledge base cleanup completed - no orphaned data found.")
        return False

def get_knowledge_bases_by_category():
    """Get knowledge bases grouped by category"""
    config = load_knowledge_config()
    active_kbs = [kb for kb in config.get("knowledge_bases", []) if kb.get("status") == "active"]
    
    categories = {}
    for kb in active_kbs:
        category = kb.get("category", "general")
        if category not in categories:
            categories[category] = []
        categories[category].append(kb)
    
    return categories

def update_knowledge_base_access(kb_id: str, access_type: str, category: str = None):
    """Update knowledge base access settings"""
    config = load_knowledge_config()
    
    for kb in config.get("knowledge_bases", []):
        if kb["id"] == kb_id:
            kb["access_type"] = access_type
            if category:
                kb["category"] = category
            save_knowledge_config(config)
            return True
    
    return False

def calculate_next_refresh(schedule: str, last_refreshed: str = None) -> str:
    """Calculate the next refresh time based on schedule"""
    if schedule == "manual":
        return None
    
    base_time = datetime.now()
    if last_refreshed:
        try:
            base_time = datetime.fromisoformat(last_refreshed)
        except:
            base_time = datetime.now()
    
    if schedule == "hourly":
        next_time = base_time + timedelta(hours=1)
    elif schedule == "daily":
        next_time = base_time + timedelta(days=1)
    elif schedule == "weekly":
        next_time = base_time + timedelta(weeks=1)
    elif schedule == "on_use":
        return "on_use"  # Special marker for refresh on each use
    else:
        return None
    
    return next_time.isoformat()

def update_refresh_schedule(kb_id: str, schedule: str) -> bool:
    """Update the refresh schedule for a knowledge base"""
    config = load_knowledge_config()
    
    for kb in config.get("knowledge_bases", []):
        if kb["id"] == kb_id:
            kb["refresh_schedule"] = schedule
            kb["next_refresh"] = calculate_next_refresh(schedule, kb.get("last_refreshed"))
            save_knowledge_config(config)
            return True
    return False

def get_knowledge_bases_due_for_refresh() -> List[Dict[str, Any]]:
    """Get knowledge bases that are due for refresh"""
    config = load_knowledge_config()
    due_kbs = []
    current_time = datetime.now()
    
    for kb in config.get("knowledge_bases", []):
        if kb.get("type") != "url" or kb.get("refresh_schedule") == "manual":
            continue
            
        next_refresh = kb.get("next_refresh")
        if next_refresh and next_refresh != "on_use":
            try:
                next_refresh_time = datetime.fromisoformat(next_refresh)
                if current_time >= next_refresh_time:
                    due_kbs.append(kb)
            except:
                continue
    
    return due_kbs

def mark_knowledge_base_refreshed(kb_id: str) -> bool:
    """Mark a knowledge base as refreshed and calculate next refresh time"""
    config = load_knowledge_config()
    
    for kb in config.get("knowledge_bases", []):
        if kb["id"] == kb_id:
            now = datetime.now().isoformat()
            kb["last_refreshed"] = now
            kb["next_refresh"] = calculate_next_refresh(kb.get("refresh_schedule", "manual"), now)
            save_knowledge_config(config)
            return True
    return False