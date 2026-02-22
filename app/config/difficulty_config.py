"""
Global Difficulty Levels Configuration

This module defines the canonical difficulty levels used across all exam profiles.
The system ships with three standard levels (1, 2, 3) but is designed to be
extensible to support additional levels (e.g., Level 0 for intro, Level 4 for synthesis).

These levels are based on Bloom's Taxonomy and provide a consistent framework
for cognitive complexity across all exams in the system.
"""

from collections import OrderedDict
from typing import Optional, Dict, List, Any


# Global canonical difficulty levels (extensible - not hardcoded to 3 levels)
# Uses OrderedDict to maintain order and allow lookup by level_id
GLOBAL_DIFFICULTY_LEVELS = OrderedDict([
    ("1", {
        "level_id": "1",
        "name": "Recall / Understanding",
        "verbs": ["define", "identify", "recognize", "list", "state"],
        "description": "Tests memorization and recognition of facts, terms, concepts, and basic definitions."
    }),
    ("2", {
        "level_id": "2",
        "name": "Application / Analysis",
        "verbs": ["apply", "analyze", "determine", "troubleshoot", "classify"],
        "description": "Tests ability to apply knowledge to realistic scenarios and analyze situations."
    }),
    ("3", {
        "level_id": "3",
        "name": "Evaluation / Judgment",
        "verbs": ["prioritize", "evaluate", "choose best", "decide first", "justify"],
        "description": "Tests ability to evaluate options and make professional judgments."
    })
])


def get_global_levels() -> OrderedDict:
    """
    Get all global difficulty levels.
    
    Returns:
        OrderedDict mapping level_id to level definition
    """
    return GLOBAL_DIFFICULTY_LEVELS


def get_level_by_id(level_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a specific difficulty level by ID.
    
    Args:
        level_id: The level identifier (e.g., "1", "2", "3")
        
    Returns:
        Level definition dict or None if not found
    """
    return GLOBAL_DIFFICULTY_LEVELS.get(level_id)


def validate_difficulty_level_reference(level_id: str) -> bool:
    """
    Validate that a level ID exists in the global registry.
    
    Args:
        level_id: The level identifier to validate
        
    Returns:
        True if level exists, False otherwise
    """
    return level_id in GLOBAL_DIFFICULTY_LEVELS


def get_all_level_ids() -> List[str]:
    """
    Get list of all valid level IDs.
    
    Returns:
        List of level ID strings in order
    """
    return list(GLOBAL_DIFFICULTY_LEVELS.keys())


def get_level_count() -> int:
    """
    Get the total number of defined difficulty levels.
    
    Returns:
        Count of difficulty levels
    """
    return len(GLOBAL_DIFFICULTY_LEVELS)
