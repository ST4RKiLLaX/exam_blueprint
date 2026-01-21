"""
Reasoning Controller Module for CISSP Question Generation

This module manages blueprint generation and rotation for diverse question creation.
It controls question types, domain selection, and reasoning modes to ensure variety
and prevent repetitive patterns in generated questions.
"""

import random
import re
from datetime import datetime
from typing import Optional, Dict, List
from collections import Counter

# Global in-memory cache for blueprint history per thread
# Structure: {thread_id: [{"question_type": str, "domain": str, "reasoning_mode": str, "timestamp": str}, ...]}
BLUEPRINT_CACHE = {}

# Hardcoded rotation lists (easily tunable)
QUESTION_TYPES = [
    "comparative",     # "Which is BEST/MOST appropriate?"
    "sequential",      # "What should be done FIRST?"
    "risk_identification",  # "What is the PRIMARY risk?"
    "control_selection",    # "Which control addresses X?"
    "exception"        # "When would X NOT apply?"
]

CISSP_DOMAINS = [
    "security_and_risk_management",
    "asset_security",
    "security_architecture",
    "communication_and_network_security",
    "identity_and_access_management",
    "security_assessment_and_testing",
    "security_operations",
    "software_development_security"
]

REASONING_MODES = [
    "governance",           # Policy/compliance lens
    "risk_based",          # Threat → control → residual
    "process",             # Lifecycle/phase-based
    "comparative_analysis" # Trade-offs between options
]

# Domain keyword mappings for hint detection
DOMAIN_KEYWORDS = {
    "security_and_risk_management": [
        "risk", "governance", "compliance", "policy", "legal", "regulation",
        "privacy", "ethics", "security program", "risk assessment", "business continuity"
    ],
    "asset_security": [
        "data classification", "asset", "ownership", "privacy", "retention",
        "data lifecycle", "handling", "destruction", "media sanitization"
    ],
    "security_architecture": [
        "architecture", "design", "model", "defense in depth", "layered security",
        "secure design", "system security", "physical security", "facility"
    ],
    "communication_and_network_security": [
        "network", "encryption", "cryptography", "protocol", "firewall",
        "vpn", "wireless", "telecommunications", "tls", "ssl", "ipsec", "tcp", "ip"
    ],
    "identity_and_access_management": [
        "access control", "authentication", "authorization", "identity",
        "iam", "rbac", "mac", "dac", "single sign-on", "sso", "federation", "privilege"
    ],
    "security_assessment_and_testing": [
        "testing", "audit", "assessment", "vulnerability", "penetration test",
        "security testing", "code review", "assessment", "evaluation", "validation"
    ],
    "security_operations": [
        "incident", "response", "monitoring", "logging", "siem", "investigation",
        "forensics", "disaster recovery", "backup", "patch", "change management"
    ],
    "software_development_security": [
        "sdlc", "development", "coding", "software", "application security",
        "secure coding", "code", "programming", "devops", "devsecops", "api"
    ]
}

# Question type templates for constraint building
QUESTION_TYPE_TEMPLATES = {
    "comparative": {
        "phrase": "Which is BEST/MOST appropriate?",
        "guidance": "Frame options as competing alternatives with varying degrees of correctness. The correct answer should represent the optimal choice given typical enterprise constraints."
    },
    "sequential": {
        "phrase": "What should be done FIRST?",
        "guidance": "Frame options as sequential steps in a process. The correct answer should reflect the proper order based on dependencies, risk priority, or governance requirements."
    },
    "risk_identification": {
        "phrase": "What is the PRIMARY risk?",
        "guidance": "Frame the scenario around a potential security issue. Options should present different risks or concerns, with the correct answer identifying the most significant threat."
    },
    "control_selection": {
        "phrase": "Which control addresses the issue?",
        "guidance": "Frame options as different security controls or countermeasures. The correct answer should be the most effective control for the specific threat or requirement."
    },
    "exception": {
        "phrase": "When would this NOT apply?",
        "guidance": "Frame options as scenarios or conditions. The correct answer should identify the exception case where a principle, control, or requirement does not apply."
    }
}

# Reasoning mode descriptions for constraint building
REASONING_MODE_DESCRIPTIONS = {
    "governance": "Use a policy and compliance lens. Frame the question in terms of governance requirements, organizational policy, regulatory compliance, or management responsibility.",
    "risk_based": "Use risk-based thinking. Frame the question in terms of: threat → vulnerability → impact → control → residual risk.",
    "process": "Use lifecycle or phase-based thinking. Frame the question in terms of process stages, implementation phases, or sequential workflows.",
    "comparative_analysis": "Use comparative analysis. Frame the question around trade-offs, comparing different approaches and their advantages/disadvantages in enterprise contexts."
}

# Domain display names
DOMAIN_DISPLAY_NAMES = {
    "security_and_risk_management": "Security and Risk Management",
    "asset_security": "Asset Security",
    "security_architecture": "Security Architecture and Engineering",
    "communication_and_network_security": "Communication and Network Security",
    "identity_and_access_management": "Identity and Access Management",
    "security_assessment_and_testing": "Security Assessment and Testing",
    "security_operations": "Security Operations",
    "software_development_security": "Software Development Security"
}


def detect_domain_hint(user_message: str) -> Optional[str]:
    """
    Detect if the user message contains hints about a specific CISSP domain.
    
    Args:
        user_message: The user's input message
        
    Returns:
        Domain name string if hint detected, None otherwise
    """
    if not user_message:
        return None
    
    message_lower = user_message.lower()
    
    # Score each domain based on keyword matches
    domain_scores = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in message_lower)
        if score > 0:
            domain_scores[domain] = score
    
    # Return domain with highest score if any matches found
    if domain_scores:
        return max(domain_scores, key=domain_scores.get)
    
    return None


def select_blueprint(thread_id: str, user_message: str, history_depth: int = 8) -> Dict[str, str]:
    """
    Select a blueprint for question generation with rotation logic.
    
    Args:
        thread_id: Thread/session identifier
        user_message: User's input message
        history_depth: Number of historical blueprints to consider for rotation
        
    Returns:
        Dictionary with question_type, domain, reasoning_mode, and subtopic
    """
    # Initialize cache for this thread if needed
    if thread_id not in BLUEPRINT_CACHE:
        BLUEPRINT_CACHE[thread_id] = []
    
    # Get recent blueprint history for this thread
    recent_blueprints = BLUEPRINT_CACHE[thread_id][-history_depth:]
    
    # 1. Domain selection: Check for user hint first
    domain_hint = detect_domain_hint(user_message)
    
    if domain_hint:
        selected_domain = domain_hint
    else:
        # Select least-recently-used domain
        used_domains = [bp["domain"] for bp in recent_blueprints]
        domain_counts = Counter(used_domains)
        
        # Find domains that haven't been used recently
        unused_domains = [d for d in CISSP_DOMAINS if d not in used_domains]
        
        if unused_domains:
            # Randomly select from unused domains
            selected_domain = random.choice(unused_domains)
        else:
            # All domains used recently, pick least frequent
            selected_domain = min(CISSP_DOMAINS, key=lambda d: domain_counts.get(d, 0))
    
    # 2. Question type selection: Least-recently-used
    used_types = [bp["question_type"] for bp in recent_blueprints]
    type_counts = Counter(used_types)
    
    # Find types that haven't been used recently
    unused_types = [t for t in QUESTION_TYPES if t not in used_types]
    
    if unused_types:
        selected_type = random.choice(unused_types)
    else:
        # All types used recently, pick least frequent
        selected_type = min(QUESTION_TYPES, key=lambda t: type_counts.get(t, 0))
    
    # 3. Reasoning mode selection: Rotate or random
    used_modes = [bp["reasoning_mode"] for bp in recent_blueprints[-3:]]
    
    # Avoid repeating the last reasoning mode
    available_modes = [m for m in REASONING_MODES if m not in used_modes[-1:]]
    
    if available_modes:
        selected_mode = random.choice(available_modes)
    else:
        selected_mode = random.choice(REASONING_MODES)
    
    # 4. Subtopic placeholder (will be extracted from outline chunks later)
    subtopic = ""
    
    return {
        "question_type": selected_type,
        "domain": selected_domain,
        "reasoning_mode": selected_mode,
        "subtopic": subtopic
    }


def build_blueprint_constraint(blueprint: Dict[str, str]) -> str:
    """
    Build a prompt constraint string from a blueprint.
    
    Args:
        blueprint: Dictionary containing question_type, domain, and reasoning_mode
        
    Returns:
        Formatted constraint string for prompt injection
    """
    question_type = blueprint.get("question_type", "comparative")
    domain = blueprint.get("domain", "security_and_risk_management")
    reasoning_mode = blueprint.get("reasoning_mode", "governance")
    subtopic = blueprint.get("subtopic", "")
    
    # Get templates and descriptions
    type_info = QUESTION_TYPE_TEMPLATES.get(question_type, QUESTION_TYPE_TEMPLATES["comparative"])
    mode_desc = REASONING_MODE_DESCRIPTIONS.get(reasoning_mode, REASONING_MODE_DESCRIPTIONS["governance"])
    domain_name = DOMAIN_DISPLAY_NAMES.get(domain, domain.replace("_", " ").title())
    
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

Ensure the question tests understanding at a managerial/strategic level, not just technical recall.
The correct answer should reflect CISSP principles: risk-based decisions, governance priorities, and enterprise-scale thinking.
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
