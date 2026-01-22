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
