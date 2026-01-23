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

def add_knowledge_base(title, description, kb_type, source, chunks_path=None, access_type="shared", category="general", refresh_schedule="manual", exam_profile_ids=None, profile_type=None, profile_domain=None, is_priority_kb=False, embedding_provider="openai", embedding_model=None, cissp_type=None, cissp_domain=None, exam_profile_id=None):
    """Add a new knowledge base to the configuration"""
    config = load_knowledge_config()
    
    # Generate unique ID
    kb_id = f"kb_{len(config['knowledge_bases'])}_{int(datetime.now().timestamp())}"
    
    # Handle backward compatibility: cissp_* params map to profile_* fields
    if profile_type is None and cissp_type is not None:
        profile_type = cissp_type
    if profile_domain is None and cissp_domain is not None:
        profile_domain = cissp_domain
    
    # Handle backward compatibility: exam_profile_id → exam_profile_ids
    if exam_profile_ids is None and exam_profile_id is not None:
        exam_profile_ids = [exam_profile_id] if exam_profile_id else []
    elif exam_profile_ids is None:
        exam_profile_ids = []
    
    new_kb = {
        "id": kb_id,
        "title": title,
        "description": description,
        "type": kb_type,
        "source": source,
        "chunks_path": chunks_path,
        "created_at": datetime.now().isoformat(),
        "exam_profile_ids": exam_profile_ids,  # List of profile IDs
        "status": "active",
        "access_type": access_type,  # "shared" or "exclusive"
        "category": category,  # "general", "cna", "pharmacy", "admin", etc.
        "refresh_schedule": refresh_schedule,  # "manual", "hourly", "daily", "weekly", "on_use"
        "last_refreshed": datetime.now().isoformat() if kb_type == "url" else None,
        "next_refresh": None,  # Will be calculated based on schedule
        "profile_type": profile_type,  # "outline", "cbk", or None (replaces cissp_type)
        "profile_domain": profile_domain,  # domain identifier string or None (replaces cissp_domain)
        "is_priority_kb": is_priority_kb,  # True for priority/hot topics KB
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

def update_knowledge_base_access(kb_id: str, access_type: str):
    """Update knowledge base access settings"""
    config = load_knowledge_config()
    
    for kb in config.get("knowledge_bases", []):
        if kb["id"] == kb_id:
            kb["access_type"] = access_type
            save_knowledge_config(config)
            return True
    
    return False