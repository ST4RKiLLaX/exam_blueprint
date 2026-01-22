"""
Exam Profile Configuration Module

This module manages exam profile definitions for different certification exams.
Profiles define question types, domains, reasoning modes, and KB structure.
"""

import json
import os
from typing import Optional, Dict, List, Any

PROFILE_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "exam_profiles.json")

# Cache for loaded profiles
_PROFILE_CACHE = None


def load_exam_profiles() -> Dict[str, Any]:
    """
    Load exam profiles configuration from JSON file.
    Results are cached for performance.
    
    Returns:
        Dictionary containing all exam profiles
    """
    global _PROFILE_CACHE
    
    if _PROFILE_CACHE is not None:
        return _PROFILE_CACHE
    
    if not os.path.exists(PROFILE_CONFIG_PATH):
        return {"profiles": []}
    
    try:
        with open(PROFILE_CONFIG_PATH, "r", encoding="utf-8") as f:
            _PROFILE_CACHE = json.load(f)
            return _PROFILE_CACHE
    except (json.JSONDecodeError, FileNotFoundError):
        return {"profiles": []}


def reload_profiles():
    """Force reload of profiles from disk (clears cache)"""
    global _PROFILE_CACHE
    _PROFILE_CACHE = None
    return load_exam_profiles()


def get_profile(profile_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a specific exam profile by ID.
    
    Args:
        profile_id: Profile identifier (e.g., "cissp_2024")
        
    Returns:
        Profile dictionary or None if not found
    """
    config = load_exam_profiles()
    profiles = config.get("profiles", [])
    
    for profile in profiles:
        if profile.get("profile_id") == profile_id:
            return profile
    
    return None


def get_all_profiles() -> List[Dict[str, Any]]:
    """
    Get all available exam profiles.
    
    Returns:
        List of profile dictionaries
    """
    config = load_exam_profiles()
    return config.get("profiles", [])


def get_profile_domains(profile_id: str) -> List[Dict[str, Any]]:
    """
    Get domains for a specific profile.
    
    Args:
        profile_id: Profile identifier
        
    Returns:
        List of domain dictionaries with id, name, and keywords
    """
    profile = get_profile(profile_id)
    if profile:
        return profile.get("domains", [])
    return []


def get_profile_question_types(profile_id: str) -> List[Dict[str, Any]]:
    """
    Get question types for a specific profile.
    
    Args:
        profile_id: Profile identifier
        
    Returns:
        List of question type dictionaries with id, phrase, and guidance
    """
    profile = get_profile(profile_id)
    if profile:
        return profile.get("question_types", [])
    return []


def get_profile_reasoning_modes(profile_id: str) -> List[Dict[str, Any]]:
    """
    Get reasoning modes for a specific profile.
    
    Args:
        profile_id: Profile identifier
        
    Returns:
        List of reasoning mode dictionaries with id, name, and description
    """
    profile = get_profile(profile_id)
    if profile:
        return profile.get("reasoning_modes", [])
    return []


def get_profile_kb_structure(profile_id: str) -> Dict[str, str]:
    """
    Get KB structure configuration for a profile.
    
    Args:
        profile_id: Profile identifier
        
    Returns:
        Dictionary with priority_kb_flag, outline_type, domain_type
    """
    profile = get_profile(profile_id)
    if profile:
        return profile.get("kb_structure", {})
    return {}


def get_domain_keywords(profile_id: str) -> Dict[str, List[str]]:
    """
    Get domain keyword mappings for hint detection.
    
    Args:
        profile_id: Profile identifier
        
    Returns:
        Dictionary mapping domain IDs to keyword lists
    """
    domains = get_profile_domains(profile_id)
    return {domain["id"]: domain.get("keywords", []) for domain in domains}


def get_question_type_template(profile_id: str, question_type_id: str) -> Optional[Dict[str, str]]:
    """
    Get question type template by ID.
    
    Args:
        profile_id: Profile identifier
        question_type_id: Question type identifier
        
    Returns:
        Dictionary with phrase and guidance, or None if not found
    """
    question_types = get_profile_question_types(profile_id)
    
    for qt in question_types:
        if qt.get("id") == question_type_id:
            return {"phrase": qt.get("phrase", ""), "guidance": qt.get("guidance", "")}
    
    return None


def get_reasoning_mode_description(profile_id: str, reasoning_mode_id: str) -> str:
    """
    Get reasoning mode description by ID.
    
    Args:
        profile_id: Profile identifier
        reasoning_mode_id: Reasoning mode identifier
        
    Returns:
        Description string or empty string if not found
    """
    reasoning_modes = get_profile_reasoning_modes(profile_id)
    
    for mode in reasoning_modes:
        if mode.get("id") == reasoning_mode_id:
            return mode.get("description", "")
    
    return ""


def get_domain_display_name(profile_id: str, domain_id: str) -> str:
    """
    Get human-readable domain name by ID.
    
    Args:
        profile_id: Profile identifier
        domain_id: Domain identifier
        
    Returns:
        Domain display name or formatted domain_id if not found
    """
    domains = get_profile_domains(profile_id)
    
    for domain in domains:
        if domain.get("id") == domain_id:
            return domain.get("name", domain_id.replace("_", " ").title())
    
    return domain_id.replace("_", " ").title()


def profile_exists(profile_id: str) -> bool:
    """
    Check if a profile exists.
    
    Args:
        profile_id: Profile identifier
        
    Returns:
        True if profile exists, False otherwise
    """
    return get_profile(profile_id) is not None


def validate_profile_structure(profile_data: Dict[str, Any]) -> tuple[bool, str]:
    """
    Validate profile data structure.
    
    Args:
        profile_data: Profile dictionary to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    required_fields = [
        "profile_id", "name", "description", "question_types",
        "domains", "reasoning_modes", "kb_structure", "guidance_suffix"
    ]
    
    # Check required top-level fields
    for field in required_fields:
        if field not in profile_data:
            return False, f"Missing required field: {field}"
    
    # Validate profile_id format (snake_case)
    profile_id = profile_data.get("profile_id", "")
    if not profile_id or not profile_id.replace("_", "").isalnum() or profile_id[0].isdigit():
        return False, "Profile ID must be snake_case alphanumeric (e.g., cissp_2024)"
    
    # Validate question_types structure
    if not isinstance(profile_data["question_types"], list):
        return False, "question_types must be a list"
    
    for qt in profile_data["question_types"]:
        if not all(k in qt for k in ["id", "phrase", "guidance"]):
            return False, "Each question type must have id, phrase, and guidance"
    
    # Validate domains structure
    if not isinstance(profile_data["domains"], list):
        return False, "domains must be a list"
    
    for domain in profile_data["domains"]:
        if not all(k in domain for k in ["id", "name", "keywords"]):
            return False, "Each domain must have id, name, and keywords"
        if not isinstance(domain["keywords"], list):
            return False, "Domain keywords must be a list"
    
    # Validate reasoning_modes structure
    if not isinstance(profile_data["reasoning_modes"], list):
        return False, "reasoning_modes must be a list"
    
    for mode in profile_data["reasoning_modes"]:
        if not all(k in mode for k in ["id", "name", "description"]):
            return False, "Each reasoning mode must have id, name, and description"
    
    # Validate kb_structure
    kb_struct = profile_data.get("kb_structure", {})
    required_kb_fields = ["priority_kb_flag", "outline_type", "domain_type"]
    for field in required_kb_fields:
        if field not in kb_struct:
            return False, f"kb_structure missing required field: {field}"
    
    return True, ""


def save_profile(profile_data: Dict[str, Any]) -> tuple[bool, str]:
    """
    Create or update an exam profile.
    
    Args:
        profile_data: Complete profile dictionary
        
    Returns:
        Tuple of (success, message)
    """
    # Validate structure
    is_valid, error_msg = validate_profile_structure(profile_data)
    if not is_valid:
        return False, error_msg
    
    profile_id = profile_data["profile_id"]
    
    # Load current profiles
    config = load_exam_profiles()
    profiles = config.get("profiles", [])
    
    # Check if updating or creating
    existing_index = None
    for idx, profile in enumerate(profiles):
        if profile.get("profile_id") == profile_id:
            existing_index = idx
            break
    
    if existing_index is not None:
        # Update existing
        profiles[existing_index] = profile_data
        action = "updated"
    else:
        # Create new
        profiles.append(profile_data)
        action = "created"
    
    # Write back to file
    config["profiles"] = profiles
    
    try:
        with open(PROFILE_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        # Reload cache
        reload_profiles()
        
        return True, f"Profile {action} successfully"
    except Exception as e:
        return False, f"Failed to save profile: {str(e)}"


def delete_profile(profile_id: str) -> tuple[bool, str]:
    """
    Delete an exam profile.
    
    Args:
        profile_id: Profile identifier to delete
        
    Returns:
        Tuple of (success, message)
    """
    # Load current profiles
    config = load_exam_profiles()
    profiles = config.get("profiles", [])
    
    # Find and remove profile
    new_profiles = [p for p in profiles if p.get("profile_id") != profile_id]
    
    if len(new_profiles) == len(profiles):
        return False, "Profile not found"
    
    config["profiles"] = new_profiles
    
    try:
        with open(PROFILE_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        # Reload cache
        reload_profiles()
        
        return True, "Profile deleted successfully"
    except Exception as e:
        return False, f"Failed to delete profile: {str(e)}"


def get_profile_usage(profile_id: str) -> Dict[str, Any]:
    """
    Get usage statistics for a profile.
    
    Args:
        profile_id: Profile identifier
        
    Returns:
        Dictionary with agents_count, kb_count, agent_ids, kb_ids
    """
    from app.models.agent import agent_manager
    from app.config.knowledge_config import load_knowledge_config
    
    # Check agents - get_all_agents() returns a list of Agent objects
    all_agents = agent_manager.get_all_agents()
    using_agents = [
        agent.agent_id for agent in all_agents
        if agent.exam_profile_id == profile_id
    ]
    
    # Check knowledge bases
    kb_config = load_knowledge_config()
    all_kbs = kb_config.get("knowledge_bases", [])
    using_kbs = [
        kb.get("id") for kb in all_kbs
        if kb.get("exam_profile_id") == profile_id
    ]
    
    return {
        "agents_count": len(using_agents),
        "kb_count": len(using_kbs),
        "agent_ids": using_agents,
        "kb_ids": using_kbs
    }
