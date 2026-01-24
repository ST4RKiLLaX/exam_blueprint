"""
Reasoning Controller Module for Exam Profile Question Generation

This module manages blueprint generation and rotation for diverse question creation.
It controls question types, domain selection, and reasoning modes to ensure variety
and prevent repetitive patterns in generated questions.

Now profile-based: loads configuration from exam profiles instead of hardcoded values.
"""

import random
import re
from datetime import datetime
from typing import Optional, Dict, List
from collections import Counter

# Global in-memory cache for blueprint history per thread
# Structure: {thread_id: [{"question_type": str, "domain": str, "reasoning_mode": str, "timestamp": str}, ...]}
BLUEPRINT_CACHE = {}


def detect_domain_hint(user_message: str, profile: Dict) -> Optional[str]:
    """
    Detect if the user message contains hints about a specific domain.
    
    Args:
        user_message: The user's input message
        profile: Exam profile dictionary with domains configuration
        
    Returns:
        Domain ID string if hint detected, None otherwise
    """
    if not user_message or not profile:
        return None
    
    message_lower = user_message.lower()
    domains = profile.get("domains", [])
    
    # Score each domain based on keyword matches
    domain_scores = {}
    for domain in domains:
        domain_id = domain.get("id")
        keywords = domain.get("keywords", [])
        score = sum(1 for keyword in keywords if keyword in message_lower)
        if score > 0:
            domain_scores[domain_id] = score
    
    # Return domain with highest score if any matches found
    if domain_scores:
        return max(domain_scores, key=domain_scores.get)
    
    return None


def normalize_weights(weights: Dict[str, float], enabled_levels: List[str]) -> Dict[str, float]:
    """
    Normalize weights to sum to 1.0 for only enabled levels.
    
    Args:
        weights: Raw weights dict from difficulty_profile
        enabled_levels: List of level IDs that are currently enabled
        
    Returns:
        Normalized weights dict summing to 1.0
    """
    # Filter to only enabled levels
    enabled_weights = {k: v for k, v in weights.items() if k in enabled_levels}
    
    total = sum(enabled_weights.values())
    if total == 0:
        # Equal distribution if all weights are 0
        return {k: 1.0/len(enabled_weights) for k in enabled_weights}
    
    # Normalize to sum to 1.0
    return {k: v/total for k, v in enabled_weights.items()}


def select_question_type_two_stage(
    thread_id: str,
    profile: Dict,
    enabled_levels: List[str],
    history_depth: int = 8
) -> Dict:
    """
    Two-stage selection: pick difficulty level by weights, then question type within level.
    
    This ensures weights control level frequency, not question type frequency.
    Prevents one level with many question types from dominating the distribution.
    
    Args:
        thread_id: Session identifier for tracking history
        profile: Exam profile with difficulty_profile and question_types
        enabled_levels: List of level_ids that are currently enabled
        history_depth: How many recent selections to track
        
    Returns:
        Selected question type dict (includes difficulty_level field)
    """
    # Get difficulty profile settings
    difficulty_profile = profile.get('difficulty_profile', {})
    raw_weights = difficulty_profile.get('weights', {})
    
    # Stage 1: Select difficulty level using normalized weights
    normalized_weights = normalize_weights(raw_weights, enabled_levels)
    
    # Get history and count recent level usage
    history = get_blueprint_history(thread_id, history_depth)
    recent_levels = [bp.get('question_type', {}).get('difficulty_level') 
                     for bp in history if bp.get('question_type')]
    level_counts = Counter(recent_levels)
    
    # Apply LRU bias to weights
    level_weights_with_bias = {}
    for level_id, weight in normalized_weights.items():
        count = level_counts.get(level_id, 0)
        bias = 1.0 / (count + 1)  # Boost underused levels
        level_weights_with_bias[level_id] = weight * bias
    
    # Normalize again after bias
    total_biased = sum(level_weights_with_bias.values())
    final_weights = {k: v/total_biased for k, v in level_weights_with_bias.items()}
    
    # Select level using weighted random
    selected_level = random.choices(
        list(final_weights.keys()),
        weights=list(final_weights.values())
    )[0]
    
    # Stage 2: Select question type within selected level
    question_types = profile.get('question_types', [])
    types_for_level = [qt for qt in question_types 
                       if qt.get('difficulty_level') == selected_level]
    
    if not types_for_level:
        # Fallback: should not happen if validation passed
        types_for_level = question_types
    
    # Get recent question type usage
    recent_type_ids = [bp.get('question_type', {}).get('id') for bp in history]
    type_counts = Counter(recent_type_ids)
    
    # LRU selection within level
    unused_types = [qt for qt in types_for_level 
                    if qt['id'] not in recent_type_ids]
    
    if unused_types:
        selected_type = random.choice(unused_types)
    else:
        # All types used recently, pick least frequent
        selected_type = min(types_for_level, 
                            key=lambda qt: type_counts.get(qt['id'], 0))
    
    return selected_type


def get_blueprint_history(thread_id: str, history_depth: int) -> List[Dict]:
    """
    Get recent blueprint history for a thread.
    
    Args:
        thread_id: Thread/session identifier
        history_depth: Number of recent blueprints to return
        
    Returns:
        List of recent blueprint dictionaries
    """
    if thread_id not in BLUEPRINT_CACHE:
        return []
    return BLUEPRINT_CACHE[thread_id][-history_depth:]


def select_blueprint(thread_id: str, user_message: str, history_depth: int, profile: Dict, enabled_levels: Optional[List[str]] = None) -> Dict[str, str]:
    """
    Select a blueprint for question generation with rotation logic.
    
    Args:
        thread_id: Thread/session identifier
        user_message: User's input message
        history_depth: Number of historical blueprints to consider for rotation
        profile: Exam profile dictionary with configuration
        enabled_levels: Optional list of enabled difficulty level IDs (defaults to all)
        
    Returns:
        Dictionary with question_type, domain, reasoning_mode, difficulty_level, and subtopic
    """
    # Initialize cache for this thread if needed
    if thread_id not in BLUEPRINT_CACHE:
        BLUEPRINT_CACHE[thread_id] = []
    
    # Get recent blueprint history for this thread
    recent_blueprints = BLUEPRINT_CACHE[thread_id][-history_depth:]
    
    # Extract profile configuration
    question_types = [qt["id"] for qt in profile.get("question_types", [])]
    domains = [d["id"] for d in profile.get("domains", [])]
    reasoning_modes = [rm["id"] for rm in profile.get("reasoning_modes", [])]
    
    # 1. Domain selection: Check for user hint first
    domain_hint = detect_domain_hint(user_message, profile)
    
    if domain_hint:
        selected_domain = domain_hint
    else:
        # Select least-recently-used domain
        used_domains = [bp["domain"] for bp in recent_blueprints]
        domain_counts = Counter(used_domains)
        
        # Find domains that haven't been used recently
        unused_domains = [d for d in domains if d not in used_domains]
        
        if unused_domains:
            # Randomly select from unused domains
            selected_domain = random.choice(unused_domains)
        else:
            # All domains used recently, pick least frequent
            selected_domain = min(domains, key=lambda d: domain_counts.get(d, 0))
    
    # 2. Question type selection with two-stage difficulty selection
    # NEW: Check if profile uses new difficulty system
    selected_question_type_dict = None
    
    if profile.get("difficulty_profile"):
        # NEW SYSTEM: Two-stage selection (level by weights → type within level)
        difficulty_prof = profile.get("difficulty_profile", {})
        
        # If no enabled_levels specified, enable all by default
        if enabled_levels is None:
            enabled_levels = difficulty_prof.get("enabled_levels", [])
        
        if enabled_levels:
            # Use two-stage selection
            selected_question_type_dict = select_question_type_two_stage(
                thread_id, profile, enabled_levels, history_depth
            )
    
    # Fallback: OLD SYSTEM or if no difficulty profile
    if not selected_question_type_dict:
        # Old LRU selection on question type IDs only
        used_types = [bp["question_type"] for bp in recent_blueprints]
        type_counts = Counter(used_types)
        
        # Find types that haven't been used recently
        unused_types = [t for t in question_types if t not in used_types]
        
        if unused_types:
            selected_type_id = random.choice(unused_types)
        else:
            # All types used recently, pick least frequent
            selected_type_id = min(question_types, key=lambda t: type_counts.get(t, 0))
        
        # For backward compatibility, just store ID
        selected_question_type_dict = {"id": selected_type_id}
    
    # 3. Reasoning mode selection: Rotate or random
    used_modes = [bp["reasoning_mode"] for bp in recent_blueprints[-3:]]
    
    # Avoid repeating the last reasoning mode
    available_modes = [m for m in reasoning_modes if m not in used_modes[-1:]]
    
    if available_modes:
        selected_mode = random.choice(available_modes)
    else:
        selected_mode = random.choice(reasoning_modes)
    
    # 4. Subtopic placeholder (will be extracted from outline chunks later)
    subtopic = ""
    
    blueprint = {
        "question_type": selected_question_type_dict,  # Full dict now, not just ID
        "domain": selected_domain,
        "reasoning_mode": selected_mode,
        "subtopic": subtopic
    }
    
    return blueprint


def build_blueprint_constraint(blueprint: Dict[str, str], profile: Dict) -> str:
    """
    Build a prompt constraint string from a blueprint.
    
    Args:
        blueprint: Dictionary containing question_type (dict or str), domain, and reasoning_mode
        profile: Exam profile dictionary with configuration
        
    Returns:
        Formatted constraint string for prompt injection
    """
    from app.config.exam_profile_config import (
        get_question_type_template,
        get_reasoning_mode_description,
        get_domain_display_name
    )
    
    question_type = blueprint.get("question_type", "")
    domain = blueprint.get("domain", "")
    reasoning_mode = blueprint.get("reasoning_mode", "")
    subtopic = blueprint.get("subtopic", "")
    profile_id = profile.get("profile_id", "")
    
    # Handle both old (string ID) and new (dict) question_type formats
    if isinstance(question_type, dict):
        # NEW: question_type is a full dict with difficulty_level
        type_info = {
            "phrase": question_type.get("phrase", ""),
            "guidance": question_type.get("guidance", "")
        }
        question_type_id = question_type.get("id", "")
    else:
        # OLD: question_type is just an ID string
        question_type_id = question_type
        type_info = get_question_type_template(profile_id, question_type_id)
        if not type_info:
            type_info = {"phrase": question_type_id, "guidance": ""}
    
    mode_desc = get_reasoning_mode_description(profile_id, reasoning_mode)
    if not mode_desc:
        mode_desc = reasoning_mode.replace('_', ' ').title()
    
    domain_name = get_domain_display_name(profile_id, domain)
    
    # Get profile-specific guidance suffix
    guidance_suffix = profile.get("guidance_suffix", "")
    
    # Build constraint text
    constraint = f"""
QUESTION CONSTRAINTS FOR THIS GENERATION:
- Question type: {type_info['phrase']}
- Domain focus: {domain_name}
- Reasoning mode: {reasoning_mode.replace('_', ' ').title()}
{f"- Subtopic focus: {subtopic}" if subtopic else ""}

GUIDANCE:
{type_info['guidance']}

{mode_desc}

{guidance_suffix}
"""
    
    return constraint


def store_blueprint(thread_id: str, blueprint: Dict[str, str], max_depth: int = 8):
    """
    Store a blueprint in the thread's history cache.
    
    Args:
        thread_id: Thread/session identifier
        blueprint: Blueprint dictionary to store
        max_depth: Maximum number of blueprints to keep in cache
    """
    # Initialize cache for this thread if needed
    if thread_id not in BLUEPRINT_CACHE:
        BLUEPRINT_CACHE[thread_id] = []
    
    # Add timestamp
    blueprint_with_timestamp = blueprint.copy()
    blueprint_with_timestamp["timestamp"] = datetime.now().isoformat()
    
    # Append to cache
    BLUEPRINT_CACHE[thread_id].append(blueprint_with_timestamp)
    
    # Trim to max depth
    if len(BLUEPRINT_CACHE[thread_id]) > max_depth:
        BLUEPRINT_CACHE[thread_id] = BLUEPRINT_CACHE[thread_id][-max_depth:]


def extract_subtopic_from_outline(outline_chunks: List[str]) -> str:
    """
    Extract a specific subtopic from outline chunks to refine retrieval query.
    
    Args:
        outline_chunks: List of outline chunk strings
        
    Returns:
        Extracted subtopic string or empty string
    """
    if not outline_chunks:
        return ""
    
    # Simple extraction: Look for numbered topics, bullet points, or key phrases
    # This is a basic implementation that can be enhanced
    
    for chunk in outline_chunks:
        # Look for patterns like "1.2.3 Topic Name" or "• Topic Name"
        patterns = [
            r'[\d\.]+\s+([A-Z][^\n\r\.]{10,80})',  # Numbered sections
            r'[•\-\*]\s+([A-Z][^\n\r\.]{10,80})',   # Bullet points
        ]
        
        for pattern in patterns:
            match = re.search(pattern, chunk)
            if match:
                subtopic = match.group(1).strip()
                # Clean up common artifacts
                subtopic = re.sub(r'\s+', ' ', subtopic)
                if len(subtopic) > 10 and len(subtopic) < 100:
                    return subtopic
    
    # Fallback: Extract first substantial sentence
    for chunk in outline_chunks:
        sentences = chunk.split('.')
        for sentence in sentences:
            clean_sentence = sentence.strip()
            if 20 < len(clean_sentence) < 150:
                return clean_sentence
    
    return ""
