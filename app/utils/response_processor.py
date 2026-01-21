"""
Response post-processing pipeline for AI agent replies.

This module provides functions to programmatically enforce format rules,
remove verbosity, and validate responses after LLM generation.
"""

import re
import numpy as np
from typing import Tuple, Dict, Optional, List

# Compile regex patterns at module load for performance
VERBOSITY_PATTERNS = [
    re.compile(r"^As an AI (language model|assistant),?\s*", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^I('m| am) (an AI|here to help|happy to assist),?\s*", re.IGNORECASE | re.MULTILINE),
    re.compile(r"I hope (this helps|that helps)\.?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"Let me know if you (need|want|would like|have).*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"Feel free to ask.*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"Is there anything else.*$", re.IGNORECASE | re.MULTILINE),
]

DISCLAIMER_PATTERNS = [
    re.compile(r"\*\*Disclaimer:?\*\*.*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"Please note:.*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"\(Note:.*?\)", re.IGNORECASE),
]


def apply_common_filters(text: str) -> str:
    """
    Apply universal verbosity filters.
    Always runs regardless of agent settings.
    
    Args:
        text: Raw response text from LLM
    
    Returns:
        Cleaned text with common verbosity patterns removed
    """
    if not text:
        return text
    
    cleaned = text
    
    # Remove common AI preambles
    for pattern in VERBOSITY_PATTERNS:
        cleaned = pattern.sub('', cleaned)
    
    # Remove disclaimers
    for pattern in DISCLAIMER_PATTERNS:
        cleaned = pattern.sub('', cleaned)
    
    # Trim excessive whitespace
    # Replace multiple newlines with maximum of 2
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    
    # Remove leading/trailing whitespace
    cleaned = cleaned.strip()
    
    return cleaned


def apply_format_rules(text: str, format_type: str) -> str:
    """
    Enforce specific output formats.
    
    Args:
        text: Text to format
        format_type: Type of format to enforce
    
    Supported formats:
    - "questions_only": Extract only question lines
    - "numbered_list": Ensure numbered format
    - "qa_pairs": Extract Q: A: pairs
    - "bullet_points": Convert to bullet list
    
    Returns:
        Formatted text
    """
    if not text or not format_type:
        return text
    
    if format_type == "questions_only":
        # Extract lines that end with '?' or are numbered questions
        lines = text.split('\n')
        questions = []
        for line in lines:
            line = line.strip()
            if line and ('?' in line or re.match(r'^\d+[\.)]\s*', line)):
                questions.append(line)
        return '\n'.join(questions)
    
    elif format_type == "numbered_list":
        # Ensure content is in numbered list format
        lines = text.split('\n')
        formatted_lines = []
        counter = 1
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Remove existing numbering if present
            line = re.sub(r'^\d+[\.)]\s*', '', line)
            line = re.sub(r'^[-•*]\s*', '', line)
            formatted_lines.append(f"{counter}. {line}")
            counter += 1
        return '\n'.join(formatted_lines)
    
    elif format_type == "qa_pairs":
        # Extract Q: A: pairs
        # Look for patterns like "Q:" or "Question:" followed by "A:" or "Answer:"
        pairs = []
        lines = text.split('\n')
        current_q = None
        current_a = None
        
        for line in lines:
            line = line.strip()
            if re.match(r'^Q(uestion)?:?\s*', line, re.IGNORECASE):
                if current_q and current_a:
                    pairs.append(f"Q: {current_q}\nA: {current_a}")
                current_q = re.sub(r'^Q(uestion)?:?\s*', '', line, flags=re.IGNORECASE)
                current_a = None
            elif re.match(r'^A(nswer)?:?\s*', line, re.IGNORECASE):
                current_a = re.sub(r'^A(nswer)?:?\s*', '', line, flags=re.IGNORECASE)
        
        if current_q and current_a:
            pairs.append(f"Q: {current_q}\nA: {current_a}")
        
        return '\n\n'.join(pairs) if pairs else text
    
    elif format_type == "bullet_points":
        # Convert to bullet point format
        lines = text.split('\n')
        formatted_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Remove existing numbering/bullets
            line = re.sub(r'^\d+[\.)]\s*', '', line)
            line = re.sub(r'^[-•*]\s*', '', line)
            formatted_lines.append(f"• {line}")
        return '\n'.join(formatted_lines)
    
    return text


def validate_response(text: str, validation_type: str) -> Tuple[str, bool]:
    """
    Validate response matches expected pattern.
    
    Args:
        text: Text to validate
        validation_type: Type of validation to apply
    
    Validations:
    - "mcq_only": Check for A/B/C/D answer
    - "yes_no_only": Check for yes/no answer
    - "numeric_only": Check for numeric answer
    
    Returns:
        Tuple of (cleaned_text, is_valid)
    """
    if not text or not validation_type:
        return text, True
    
    cleaned = text.strip()
    
    if validation_type == "mcq_only":
        # Look for A, B, C, or D (case insensitive)
        match = re.search(r'\b([A-D])\b', cleaned, re.IGNORECASE)
        if match:
            # Extract just the letter
            return match.group(1).upper(), True
        return cleaned, False
    
    elif validation_type == "yes_no_only":
        # Look for yes or no (case insensitive)
        cleaned_lower = cleaned.lower()
        if 'yes' in cleaned_lower and 'no' not in cleaned_lower:
            return "Yes", True
        elif 'no' in cleaned_lower and 'yes' not in cleaned_lower:
            return "No", True
        return cleaned, False
    
    elif validation_type == "numeric_only":
        # Extract numeric value
        match = re.search(r'-?\d+\.?\d*', cleaned)
        if match:
            return match.group(0), True
        return cleaned, False
    
    return cleaned, True


def limit_sentences(text: str, max_sentences: int) -> str:
    """
    Limit response to maximum number of sentences.
    
    Args:
        text: Text to limit
        max_sentences: Maximum number of sentences to keep
    
    Returns:
        Truncated text
    """
    if not text or not max_sentences or max_sentences <= 0:
        return text
    
    # Split on sentence boundaries (., !, ?)
    sentences = re.split(r'([.!?]+\s+)', text)
    
    # Rejoin sentence pairs (text + delimiter)
    full_sentences = []
    for i in range(0, len(sentences) - 1, 2):
        full_sentences.append(sentences[i] + (sentences[i + 1] if i + 1 < len(sentences) else ''))
    
    # Handle last sentence if no delimiter
    if len(sentences) % 2 == 1:
        full_sentences.append(sentences[-1])
    
    # Keep only first N sentences
    limited = ''.join(full_sentences[:max_sentences])
    return limited.strip()


def strip_markdown(text: str) -> str:
    """
    Remove markdown formatting from text.
    
    Args:
        text: Text with markdown
    
    Returns:
        Plain text without markdown
    """
    if not text:
        return text
    
    # Remove bold/italic
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    
    # Remove links but keep text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # Remove code blocks
    text = re.sub(r'```[^`]*```', '', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    
    # Remove headers
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
    
    return text


def extract_response_patterns(text: str) -> Dict[str, str]:
    """
    Extract structural patterns from response for repetition detection.
    
    Args:
        text: Response text to analyze
    
    Returns:
        Dict with:
        - "role_pattern": Normalized role phrase (first 50 chars)
        - "structure_pattern": Decision/format markers
    """
    patterns = {
        "role_pattern": "",
        "structure_pattern": ""
    }
    
    if not text or len(text) < 50:
        return patterns
    
    # Extract role pattern from opening (first 2 sentences)
    sentences = text.split('.')[:2]
    opening = '.'.join(sentences).lower()
    
    # Common role patterns
    role_markers = [
        r'as an? \w+',
        r'i am an? \w+',
        r'being an? \w+',
        r'as your \w+'
    ]
    
    for marker in role_markers:
        match = re.search(marker, opening)
        if match:
            patterns["role_pattern"] = match.group(0)
            break
    
    # Extract structure pattern (decision markers, formatting)
    structure_markers = [
        r'i (believe|think) (the answer is|that)',
        r'(therefore|thus|hence)',
        r'based on',
        r'the (correct |best )?answer is',
        r'^[A-D]\)',  # MCQ format
        r'^\d+\.',    # Numbered list
        r'^[-•]',     # Bullets
    ]
    
    for marker in structure_markers:
        if re.search(marker, text.lower(), re.MULTILINE):
            patterns["structure_pattern"] = marker
            break
    
    return patterns


def patterns_match(patterns1: Dict, patterns2: Dict) -> bool:
    """
    Check if two pattern dicts indicate repetition.
    Returns True if patterns are too similar.
    
    Args:
        patterns1: First pattern dict
        patterns2: Second pattern dict
    
    Returns:
        True if patterns indicate repetition
    """
    # Both must have at least one pattern
    if not patterns1 or not patterns2:
        return False
    
    # Check role pattern match
    role_match = (patterns1.get("role_pattern") and 
                  patterns1.get("role_pattern") == patterns2.get("role_pattern"))
    
    # Check structure pattern match
    structure_match = (patterns1.get("structure_pattern") and 
                      patterns1.get("structure_pattern") == patterns2.get("structure_pattern"))
    
    # Repetition if BOTH patterns match
    return role_match and structure_match


def extract_question_signature(text: str) -> str:
    """
    Extract question stem + correct answer for semantic comparison.
    
    Looks for:
    - Question text (usually ends with ?)
    - Correct answer marker (often "Correct:", "Answer:", or letter in bold)
    
    Returns:
        "Question stem\nCorrect: X" or empty string if not found
    """
    if not text:
        return ""
    
    lines = text.strip().split('\n')
    question_stem = ""
    correct_answer = ""
    
    # Find question (usually has ?)
    for line in lines:
        if '?' in line:
            question_stem = line.strip()
            break
    
    # Find correct answer marker
    # Common patterns: "Correct: B", "Answer: C", "**B**", etc.
    patterns = [
        r'(?:Correct|Answer):\s*([A-D])',
        r'\*\*([A-D])\*\*',
        r'^([A-D])\)',  # If marked as "B) Text" in explanation
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            correct_answer = match.group(1).upper()
            break
    
    if question_stem and correct_answer:
        return f"{question_stem}\nCorrect: {correct_answer}"
    
    return ""


def generate_signature_embedding(signature_text: str) -> Optional[np.ndarray]:
    """
    Generate embedding for question signature.
    Uses OpenAI embeddings (text-embedding-3-large) by default.
    
    Returns:
        numpy array or None if generation fails
    """
    if not signature_text:
        return None
    
    try:
        from app.utils.knowledge_processor import create_embedding
        
        # Use OpenAI embeddings for semantic repetition detection
        # (could make this configurable per agent in future)
        embedding = create_embedding(signature_text, provider="openai")
        return embedding
    except Exception as e:
        print(f"[ERROR] Embedding generation failed: {e}")
        return None


def check_semantic_repetition(current_embedding: np.ndarray, 
                              cached_embeddings: List[np.ndarray],
                              threshold: float = 0.90) -> Tuple[bool, float]:
    """
    Check if current embedding is too similar to any cached embeddings.
    
    Args:
        current_embedding: Embedding of current response
        cached_embeddings: List of recent embeddings
        threshold: Similarity threshold (0.90 recommended)
    
    Returns:
        (is_repetitive, max_similarity)
    """
    if current_embedding is None or not cached_embeddings:
        return False, 0.0
    
    from numpy.linalg import norm
    
    max_similarity = 0.0
    
    for cached in cached_embeddings:
        if cached is None:
            continue
        
        # Cosine similarity
        similarity = np.dot(current_embedding, cached) / (norm(current_embedding) * norm(cached))
        max_similarity = max(max_similarity, similarity)
        
        if similarity > threshold:
            return True, similarity
    
    return False, max_similarity


def post_process_response(text: str, agent) -> Tuple[str, bool]:
    """
    Main post-processing pipeline.
    
    Steps:
    1. Apply common filters (always)
    2. Apply agent-specific rules (if configured)
    3. Validate format (if rules specify)
    4. Apply length limits (if configured)
    5. Final cleanup
    
    Args:
        text: Raw response from LLM
        agent: Agent object with post_processing_rules
    
    Returns:
        Tuple of (processed_text, validation_passed)
        validation_passed is False only if validation was configured AND failed
    """
    if not text:
        return text, True
    
    # Step 1: Always apply common filters (universal wins)
    cleaned = apply_common_filters(text)
    
    # Track if validation failed
    validation_failed = False
    
    # Step 2: Apply agent-specific rules if configured
    if agent and hasattr(agent, 'post_processing_rules') and agent.post_processing_rules:
        rules = agent.post_processing_rules
        
        # Format enforcement
        if rules.get("enforce_format"):
            cleaned = apply_format_rules(cleaned, rules["enforce_format"])
        
        # Validation
        if rules.get("validation"):
            cleaned, is_valid = validate_response(cleaned, rules["validation"])
            if not is_valid:
                validation_failed = True
                # No warning, no logging - caller will handle retry
        
        # Length limits
        if rules.get("max_sentences"):
            try:
                max_sent = int(rules["max_sentences"])
                cleaned = limit_sentences(cleaned, max_sent)
            except (ValueError, TypeError):
                pass
        
        # Strip markdown if requested
        if rules.get("strip_markdown"):
            cleaned = strip_markdown(cleaned)
    
    # Final cleanup - trim whitespace
    cleaned = cleaned.strip()
    
    return cleaned, not validation_failed
