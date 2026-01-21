import os
import numpy as np
from openai import OpenAI
from dotenv import load_dotenv
import tiktoken
from datetime import datetime
from flask import g
from app.utils.response_processor import (
    post_process_response, 
    extract_response_patterns, 
    patterns_match,
    extract_question_signature,
    generate_signature_embedding,
    check_semantic_repetition
)
# Default configuration for fallback when no agent is specified
DEFAULT_CONFIG = {
    "personality": "You are a helpful AI assistant.",
    "style": "Use a professional and friendly tone.",
    "prompt": "Please provide helpful and accurate responses."
}
from app.config.knowledge_config import get_active_knowledge_bases, get_knowledge_bases_for_agent
from app.utils.knowledge_processor import search_knowledge_base, EMBEDDING_MODEL
from app.config.model_config import get_current_model, get_current_temperature, get_model_parameters, should_use_responses_api
from app.utils.secure_access import secure_knowledge_base_access


load_dotenv()

# Global in-memory cache for semantic embeddings per thread
# Structure: {thread_id: [{"embedding": np.array, "timestamp": str}, ...]}
SEMANTIC_CACHE = {}


def truncate_history_by_tokens(history: list, max_tokens: int, encoding_name: str = "cl100k_base") -> list:
    """
    Truncate conversation history to fit within token budget.
    Keeps most recent messages that fit within limit.
    
    Args:
        history: List of message dictionaries with 'role' and 'content' keys
        max_tokens: Maximum token budget for the history
        encoding_name: Tiktoken encoding name (default: cl100k_base for GPT-4/3.5)
    
    Returns:
        List of messages that fit within the token budget
    """
    if not history:
        return []
    
    try:
        encoding = tiktoken.get_encoding(encoding_name)
    except Exception as e:
        print(f"[WARN] Could not load tiktoken encoding '{encoding_name}': {e}")
        print("Falling back to message count limit (last 5 messages)")
        return history[-5:]
    
    # Work backwards through history, keeping messages that fit
    selected_messages = []
    current_tokens = 0
    
    # Start from most recent messages
    for message in reversed(history):
        role = "User" if message.get("role") == "user" else "Assistant"
        content = message.get("content", "")
        
        # Format the message as it will appear in the prompt
        formatted_message = f"{role}: {content}"
        
        # Count tokens in this message
        try:
            message_tokens = len(encoding.encode(formatted_message))
        except Exception as e:
            print(f"[WARN] Could not encode message: {e}")
            # Rough estimate: ~4 chars per token
            message_tokens = len(formatted_message) // 4
        
        # Check if adding this message would exceed the budget
        if current_tokens + message_tokens > max_tokens:
            # If we have no messages yet and this single message exceeds budget, truncate it
            if not selected_messages:
                try:
                    # Calculate how many tokens we can fit
                    tokens = encoding.encode(formatted_message)
                    truncated_tokens = tokens[:max_tokens]
                    truncated_content = encoding.decode(truncated_tokens)
                    
                    # Create truncated message
                    truncated_message = message.copy()
                    truncated_message["content"] = truncated_content + "... [truncated]"
                    selected_messages.append(truncated_message)
                except Exception as e:
                    print(f"[WARN] Could not truncate message: {e}")
                    # Fall back to character truncation
                    char_limit = max_tokens * 4  # Rough estimate
                    truncated_message = message.copy()
                    truncated_message["content"] = content[:char_limit] + "... [truncated]"
                    selected_messages.append(truncated_message)
            break
        
        # Add this message to our selection
        selected_messages.append(message)
        current_tokens += message_tokens
    
    # Reverse to restore chronological order
    selected_messages.reverse()
    
    return selected_messages

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
        model=EMBEDDING_MODEL
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

def calculate_text_overlap(text1: str, text2: str) -> float:
    """Calculate Jaccard similarity between two text strings
    
    Returns:
        Float between 0.0 and 1.0 representing overlap ratio
        0.0 = no overlap, 1.0 = identical
    """
    if not text1 or not text2:
        return 0.0
    
    # Tokenize into words and convert to sets
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    
    # Calculate Jaccard similarity: intersection / union
    intersection = len(words1 & words2)
    union = len(words1 | words2)
    
    if union == 0:
        return 0.0
    
    return intersection / union

def cissp_two_stage_retrieval(query: str, blueprint: dict, agent) -> list:
    """
    CISSP-specific two-stage retrieval: Outline KB → Domain-specific CBK KB.
    
    Stage A: Retrieve 1-2 chunks from Outline KB for scope
    Stage B: Retrieve 2-4 chunks from domain-specific CBK KB for content
    
    Args:
        query: User's query string
        blueprint: Blueprint dict with domain selection
        agent: Agent configuration object
        
    Returns:
        List of formatted strings with KB source attribution
    """
    from app.utils.reasoning_controller import extract_subtopic_from_outline
    
    if not agent or not agent.knowledge_bases:
        return []
    
    # Get all agent's assigned KBs
    knowledge_bases = get_knowledge_bases_for_agent(agent.agent_id, agent.knowledge_bases)
    
    # Find Outline KB (cissp_type == "outline")
    outline_kb = None
    for kb in knowledge_bases:
        if kb.get("cissp_type") == "outline":
            outline_kb = kb
            break
    
    # Find Domain CBK KB (cissp_type == "cbk" AND cissp_domain matches blueprint)
    domain_cbk_kb = None
    blueprint_domain = blueprint.get("domain")
    for kb in knowledge_bases:
        if kb.get("cissp_type") == "cbk" and kb.get("cissp_domain") == blueprint_domain:
            domain_cbk_kb = kb
            break
    
    formatted_results = []
    outline_chunks_raw = []
    
    # Stage A: Retrieve from Outline KB (if available)
    if outline_kb:
        outline_results = search_knowledge_base(outline_kb["id"], query, top_k=2)
        if outline_results:
            # Extract just the chunk text for subtopic extraction
            outline_chunks_raw = [chunk for chunk, distance, kb_id in outline_results]
            
            # Format outline chunks with source
            for chunk, distance, kb_id in outline_results:
                if distance <= agent.min_similarity_threshold:
                    formatted_chunk = f"{chunk}\n[Source: {outline_kb.get('title', 'CISSP Outline')}]"
                    formatted_results.append(formatted_chunk)
    
    # Extract subtopic from outline chunks
    subtopic = extract_subtopic_from_outline(outline_chunks_raw)
    
    # Stage B: Retrieve from Domain CBK KB (if available)
    if domain_cbk_kb:
        # Refine query with subtopic
        refined_query = f"{query} {subtopic}" if subtopic else query
        
        cbk_results = search_knowledge_base(domain_cbk_kb["id"], refined_query, top_k=4)
        if cbk_results:
            # Format CBK chunks with source
            for chunk, distance, kb_id in cbk_results:
                if distance <= agent.min_similarity_threshold:
                    formatted_chunk = f"{chunk}\n[Source: {domain_cbk_kb.get('title', 'CISSP CBK')}]"
                    formatted_results.append(formatted_chunk)
    
    # If no results from either stage, return message
    if not formatted_results:
        return ["No relevant knowledge base information found for this query."]
    
    return formatted_results


def search_agent_knowledge_bases(query, agent, top_k=3):
    """
    SECURE SEARCH with global ranking and deduplication.
    
    Searches all agent-assigned knowledge bases, ranks results globally by similarity,
    deduplicates overlapping chunks, and returns top N overall results.
    
    Returns:
        List of formatted strings with KB source attribution
    """
    # Check if agent has CISSP mode enabled
    if hasattr(agent, 'enable_cissp_mode') and agent.enable_cissp_mode:
        # Use blueprint from request context (set by generate_reply)
        try:
            try:
                blueprint = getattr(g, 'current_blueprint', None)
            except RuntimeError:
                blueprint = None
        except RuntimeError:
            blueprint = None
        if blueprint:
            return cissp_two_stage_retrieval(query, blueprint, agent)
    
    # Fall back to standard retrieval for non-CISSP agents
    if not agent:
        print("🚫 SECURITY: No agent specified - denying all knowledge base access")
        return []
    
    if not agent.knowledge_bases:
        print(f"🚫 SECURITY: Agent '{agent.name}' has no assigned knowledge bases - denying all access")
        return []
    
    # STRICT: Only agent-assigned knowledge bases
    knowledge_bases = get_knowledge_bases_for_agent(agent.agent_id, agent.knowledge_bases)
    
    # Create KB lookup for titles
    kb_lookup = {kb["id"]: kb.get("title", "Unknown Source") for kb in knowledge_bases}
    
    # Step 1: Group KBs by embedding provider for efficient search
    from app.utils.knowledge_processor import create_embedding, search_knowledge_base_with_embedding
    
    provider_groups = {}
    for kb in knowledge_bases:
        provider = kb.get("embedding_provider", "openai")
        if provider not in provider_groups:
            provider_groups[provider] = []
        provider_groups[provider].append(kb)
    
    # Step 2: Search each provider group with appropriate embedding
    all_results = []
    for provider, kbs in provider_groups.items():
        try:
            # Generate query embedding for this provider
            query_embedding = create_embedding(query, provider=provider)
            
            # Search all KBs in this provider group
            for kb in kbs:
                kb_results = search_knowledge_base_with_embedding(kb["id"], query_embedding, top_k)
                if kb_results:
                    all_results.extend(kb_results)
        except Exception as e:
            print(f"[ERROR] Searching {provider} knowledge bases: {e}")
    
    if not all_results:
        return []
    
    # Step 2: Sort globally by distance (ascending - lower distance = more similar)
    all_results.sort(key=lambda x: x[1])
    
    # Step 2.5: Filter by similarity threshold (quality gate)
    filtered_results = [
        (chunk, distance, kb_id) 
        for chunk, distance, kb_id in all_results 
        if distance <= agent.min_similarity_threshold
    ]
    
    # If nothing meets threshold, return explicit message
    if not filtered_results:
        return ["No relevant knowledge base information found for this query."]
    
    # Step 3: Deduplicate using text overlap threshold
    selected_chunks = []
    selected_texts = []
    overlap_threshold = 0.7
    
    for chunk, distance, kb_id in filtered_results:
        # Check if this chunk overlaps significantly with any already-selected chunk
        is_duplicate = False
        for selected_text in selected_texts:
            if calculate_text_overlap(chunk, selected_text) > overlap_threshold:
                is_duplicate = True
                break
        
        if not is_duplicate:
            selected_chunks.append((chunk, distance, kb_id))
            selected_texts.append(chunk)
            
            # Step 4: Stop when we reach the agent's max_knowledge_chunks limit
            if len(selected_chunks) >= agent.max_knowledge_chunks:
                break
    
    # Step 5: Format results with KB source footer
    formatted_results = []
    for chunk, distance, kb_id in selected_chunks:
        kb_title = kb_lookup.get(kb_id, "Unknown Source")
        formatted_chunk = f"{chunk}\n[Source: {kb_title}]"
        formatted_results.append(formatted_chunk)
    
    return formatted_results


def build_prompt(message_body, history=None, agent=None):
    """
    Build a prompt for the AI agent to generate a reply.
    
    Args:
        message_body: The user's message/query
        history: Optional conversation history
        agent: Optional agent configuration
    
    Returns:
        Formatted prompt string
    """
    # SECURITY: Require agent for knowledge base access
    if not agent:
        print("🚫 SECURITY: No agent specified - denying all knowledge base access")
        knowledge_refs = []
        agent_prompt = DEFAULT_CONFIG.get("prompt", "")
    else:
        agent_prompt = agent.prompt or DEFAULT_CONFIG.get("prompt", "")
        
        # Search agent's assigned knowledge bases
        knowledge_refs = search_agent_knowledge_bases(message_body, agent)
    
    # Build prompt sections in optimal order
    
    # 1. Agent identity
    agent_identity = ""
    if agent:
        agent_identity = f"AGENT IDENTITY:\n---\nYou are {agent.name}, an AI assistant.\n"
    
    # 2. Agent instructions (positioned early to anchor behavior)
    agent_instructions = f"\nAGENT INSTRUCTIONS:\n---\n{agent_prompt}\n"
    
    # 2.5. Blueprint constraint (if CISSP mode)
    try:
        blueprint_constraint = getattr(g, 'blueprint_constraint', None)
    except RuntimeError:
        blueprint_constraint = None
    if blueprint_constraint:
        agent_instructions += f"\n{blueprint_constraint}\n"
    
    # 3. Formatting rules (establishes output expectations)
    formatting_rules = ""
    if agent and agent.formatting:
        formatting_rules = f"\nFORMATTING RULES:\n---\n{agent.formatting}\n"
    
    # 4. Knowledge base chunks (supports instructions, doesn't override them)
    kb_context = ""
    if knowledge_refs:
        kb_context = "\nKNOWLEDGE BASE INFORMATION:\n---\n" + "\n".join(knowledge_refs) + "\n"
    
    # 5. Conversation history (token-limited, recent context only)
    convo = ""
    if history:
        # Use agent's token budget, or default to 1000 tokens
        token_budget = agent.conversation_history_tokens if agent else 1000
        truncated_history = truncate_history_by_tokens(history, token_budget)
        
        lines = []
        for m in truncated_history:
            role = "User" if m.get("role") == "user" else "Assistant"
            content = m.get("content", "")
            lines.append(f"{role}: {content}")
        if lines:
            convo = "\nCONVERSATION HISTORY:\n---\n" + "\n".join(lines) + "\n"
    
    # 6. Current message
    return f"""
{agent_identity}{agent_instructions}{formatting_rules}{kb_context}
CURRENT MESSAGE:
---
{message_body}

{convo}
Reply:
"""

def generate_reply(message_body, history=None, agent=None, skip_post_processing=False):
    """
    Generate a reply from an AI agent based on the user's message.
    
    Args:
        message_body: The user's message/query
        history: Optional conversation history
        agent: Agent configuration object
        skip_post_processing: If True, return raw response without post-processing (for JSON output)
    
    Returns:
        Generated reply string
    """
    # SECURITY: Require agent for all operations
    if not agent:
        print("🚫 SECURITY: No agent specified - denying reply generation")
        return "🚫 ACCESS DENIED: No agent specified. Please select an agent to generate a reply."
    
    # Route to appropriate provider
    provider = getattr(agent, 'provider', 'openai')
    
    if provider == "gemini":
        return _generate_with_gemini(message_body, history, agent, skip_post_processing)
    elif provider == "openai":
        return _generate_with_openai(message_body, history, agent, skip_post_processing)
    else:
        print(f"[WARN] Unsupported provider: {provider}, falling back to OpenAI")
        return _generate_with_openai(message_body, history, agent, skip_post_processing)


def _generate_with_openai(message_body, history=None, agent=None, skip_post_processing=False):
    """
    Generate reply using OpenAI (Responses API or Chat Completions API).
    This is the original generation logic.
    """
    # SECURITY: Already checked in generate_reply
    if not agent:
        print("🚫 SECURITY: No agent specified - denying reply generation")
        return "🚫 ACCESS DENIED: No agent specified. Please select an agent to generate a reply."
    
    # Use agent-specific personality and style
    personality = agent.personality or DEFAULT_CONFIG["personality"]
    style = agent.style or DEFAULT_CONFIG["style"]
    
    # Automatically inject agent identity into the system message
    agent_identity = f"You are {agent.name}, an AI assistant. "
    system_message = agent_identity + personality + "\n" + style

    # Blueprint generation for CISSP mode
    if agent and hasattr(agent, 'enable_cissp_mode') and agent.enable_cissp_mode:
        from app.utils.reasoning_controller import select_blueprint, build_blueprint_constraint
        
        try:
            thread_id = getattr(g, 'thread_id', 'default')
        except RuntimeError:
            thread_id = 'default'
        blueprint = select_blueprint(thread_id, message_body, agent.blueprint_history_depth)
        
        # Store in request context for retrieval function to access (if in request context)
        try:
            g.current_blueprint = blueprint
        except RuntimeError:
            pass
        
        # Build constraint text
        blueprint_constraint = build_blueprint_constraint(blueprint)
        
        # Store constraint for prompt injection (if in request context)
        try:
            g.blueprint_constraint = blueprint_constraint
        except RuntimeError:
            pass

    prompt = build_prompt(message_body, history=history, agent=agent)
    
    # SECURITY: If no knowledge base access was granted, block the reply
    if not agent and "KNOWLEDGE BASE INFORMATION:" in prompt and "---" in prompt:
        kb_content = prompt.split("KNOWLEDGE BASE INFORMATION:")[1].split("SCHEDULE INFORMATION:")[0]
        if kb_content.strip() == "---":
            print("🚫 SECURITY: No knowledge base access - blocking reply generation")
            return "🚫 ACCESS DENIED: No knowledge base access granted. Please select an agent with proper permissions."
    
    # Get model-specific parameter configuration
    model_config = get_model_parameters(agent.model)
    use_responses_api = should_use_responses_api(agent.model)
    
    if use_responses_api:
        # Use Responses API for GPT-5.x models
        api_params = {
            "model": agent.model,
            "input": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ]
        }
        
        # Determine if reasoning effort is being used (and not "none")
        has_reasoning = (agent.reasoning_effort is not None and 
                        agent.reasoning_effort.lower() != "none")
        
        # For GPT-5.x with reasoning effort: exclude temperature, top_p, penalties
        # For GPT-5.x without reasoning effort: include temperature, top_p
        if not has_reasoning:
            # Standard sampling parameters allowed when reasoning is disabled
            if agent.temperature is not None:
                api_params["temperature"] = agent.temperature
            if agent.top_p is not None:
                api_params["top_p"] = agent.top_p
            
            # Penalties allowed for GPT-5.1/5 without reasoning
            if model_config["supports_penalties"]:
                if agent.frequency_penalty is not None:
                    api_params["frequency_penalty"] = agent.frequency_penalty
                if agent.presence_penalty is not None:
                    api_params["presence_penalty"] = agent.presence_penalty
        
        # Token limits for Responses API
        # Responses API uses max_output_tokens, not max_completion_tokens
        if agent.max_output_tokens is not None:
            api_params["max_output_tokens"] = agent.max_output_tokens
        elif agent.max_completion_tokens is not None:
            api_params["max_output_tokens"] = agent.max_completion_tokens
        elif agent.max_tokens is not None:
            api_params["max_output_tokens"] = agent.max_tokens
        
        # Reasoning effort (nested parameter format)
        if has_reasoning:
            api_params["reasoning"] = {"effort": agent.reasoning_effort}
        
        # Verbosity (nested parameter format for GPT-5.2)
        if agent.model.lower() == "gpt-5.2" and agent.verbosity is not None:
            api_params["text"] = {"verbosity": agent.verbosity}
        
        # Stop sequences
        if agent.stop is not None:
            api_params["stop"] = agent.stop
        
        # Call Responses API
        response = _get_openai_client().responses.create(**api_params)
        raw_response = response.output_text.strip()
        
        if skip_post_processing:
            return raw_response
        
        processed, validation_ok = post_process_response(raw_response, agent)
        
        # If validation failed and agent has validation rules, retry once
        if not validation_ok and agent.post_processing_rules.get("validation"):
            try:
                # Regenerate with same parameters
                response = _get_openai_client().responses.create(**api_params)
                raw_response = response.output_text.strip()
                processed, _ = post_process_response(raw_response, agent)
                # Return second attempt regardless of validation status
            except Exception:
                # If retry fails, return first attempt
                pass
        
        # Check for repetition with last assistant response (phrase-level)
        if history and len(history) > 0:
            # Get last assistant message
            last_assistant_msg = None
            for msg in reversed(history):
                if msg.get("role") == "assistant":
                    last_assistant_msg = msg.get("content", "")
                    break
            
            if last_assistant_msg:
                # Extract patterns from both responses
                current_patterns = extract_response_patterns(processed)
                last_patterns = extract_response_patterns(last_assistant_msg)
                
                # If patterns match, regenerate once
                if patterns_match(current_patterns, last_patterns):
                    try:
                        # Regenerate with same parameters
                        response = _get_openai_client().responses.create(**api_params)
                        raw_response = response.output_text.strip()
                        processed, _ = post_process_response(raw_response, agent)
                        # Don't check repetition again (max 1 retry)
                    except Exception:
                        # If retry fails, return first attempt
                        pass
        
        # Semantic repetition check (if enabled for agent)
        if (agent and 
            hasattr(agent, 'enable_semantic_detection') and 
            agent.enable_semantic_detection):
            
            # Extract question signature
            signature = extract_question_signature(processed)
            
            if signature:
                # Generate embedding
                current_embedding = generate_signature_embedding(signature)
                
                if current_embedding is not None:
                    # Get thread ID from request context (if available)
                    try:
                        thread_id = getattr(g, 'thread_id', 'default')
                    except RuntimeError:
                        thread_id = 'default'
                    
                    # Get cached embeddings for this thread
                    if thread_id not in SEMANTIC_CACHE:
                        SEMANTIC_CACHE[thread_id] = []
                    
                    cached_embeddings = [entry["embedding"] for entry in SEMANTIC_CACHE[thread_id]]
                    
                    # Check similarity
                    threshold = getattr(agent, 'semantic_similarity_threshold', 0.90)
                    is_repetitive, max_sim = check_semantic_repetition(
                        current_embedding, 
                        cached_embeddings, 
                        threshold
                    )
                    
                    # Log similarity for monitoring
                    print(f"[DEBUG] Semantic check: similarity={max_sim:.3f}, threshold={threshold:.3f}, regenerated={is_repetitive}")
                    
                    if is_repetitive:
                        # Regenerate with constraint
                        constraint = f"""
IMPORTANT: Your previous questions were semantically similar (similarity: {max_sim:.2f}).
Generate a question that uses a different reasoning approach and resolution strategy.
Do not reuse the same control objective or decision logic.
"""
                        
                        # Append constraint to prompt
                        try:
                            # Modify api_params for regeneration
                            api_params["input"][1]["content"] = prompt + "\n\n" + constraint
                            
                            response = _get_openai_client().responses.create(**api_params)
                            raw_response = response.output_text.strip()
                            processed, _ = post_process_response(raw_response, agent)
                            
                            # Regenerate embedding for new response
                            new_signature = extract_question_signature(processed)
                            if new_signature:
                                current_embedding = generate_signature_embedding(new_signature)
                        except Exception as e:
                            print(f"[WARN] Semantic retry failed: {e}")
                            pass  # Keep first attempt
                    
                    # Store embedding in cache (limit to last N)
                    max_depth = getattr(agent, 'semantic_history_depth', 5)
                    SEMANTIC_CACHE[thread_id].append({
                        "embedding": current_embedding,
                        "timestamp": datetime.now().isoformat()
                    })
                    
                    # Trim cache to max depth
                    if len(SEMANTIC_CACHE[thread_id]) > max_depth:
                        SEMANTIC_CACHE[thread_id] = SEMANTIC_CACHE[thread_id][-max_depth:]
        
        return processed
    
    else:
        # Use Chat Completions API for GPT-4.x and GPT-3.5
        api_params = {
            "model": agent.model,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ]
        }
        
        # Add temperature if supported
        if agent.temperature is not None:
            api_params["temperature"] = agent.temperature
        
        # Add top_p if specified
        if agent.top_p is not None:
            api_params["top_p"] = agent.top_p
        
        # Token limits
        if agent.max_tokens is not None:
            api_params["max_tokens"] = agent.max_tokens
        
        # Penalties
        if agent.frequency_penalty is not None:
            api_params["frequency_penalty"] = agent.frequency_penalty
        if agent.presence_penalty is not None:
            api_params["presence_penalty"] = agent.presence_penalty
        
        # Stop sequences
        if agent.stop is not None:
            api_params["stop"] = agent.stop
        
        # Call Chat Completions API
        response = _get_openai_client().chat.completions.create(**api_params)
        raw_response = response.choices[0].message.content.strip()
        
        if skip_post_processing:
            return raw_response
        
        processed, validation_ok = post_process_response(raw_response, agent)
        
        # If validation failed and agent has validation rules, retry once
        if not validation_ok and agent.post_processing_rules.get("validation"):
            try:
                # Regenerate with same parameters
                response = _get_openai_client().chat.completions.create(**api_params)
                raw_response = response.choices[0].message.content.strip()
                processed, _ = post_process_response(raw_response, agent)
                # Return second attempt regardless of validation status
            except Exception:
                # If retry fails, return first attempt
                pass
        
        # Check for repetition with last assistant response (phrase-level)
        if history and len(history) > 0:
            # Get last assistant message
            last_assistant_msg = None
            for msg in reversed(history):
                if msg.get("role") == "assistant":
                    last_assistant_msg = msg.get("content", "")
                    break
            
            if last_assistant_msg:
                # Extract patterns from both responses
                current_patterns = extract_response_patterns(processed)
                last_patterns = extract_response_patterns(last_assistant_msg)
                
                # If patterns match, regenerate once
                if patterns_match(current_patterns, last_patterns):
                    try:
                        # Regenerate with same parameters
                        response = _get_openai_client().chat.completions.create(**api_params)
                        raw_response = response.choices[0].message.content.strip()
                        processed, _ = post_process_response(raw_response, agent)
                        # Don't check repetition again (max 1 retry)
                    except Exception:
                        # If retry fails, return first attempt
                        pass
        
        # Semantic repetition check (if enabled for agent)
        if (agent and 
            hasattr(agent, 'enable_semantic_detection') and 
            agent.enable_semantic_detection):
            
            # Extract question signature
            signature = extract_question_signature(processed)
            
            if signature:
                # Generate embedding
                current_embedding = generate_signature_embedding(signature)
                
                if current_embedding is not None:
                    # Get thread ID from request context (if available)
                    try:
                        thread_id = getattr(g, 'thread_id', 'default')
                    except RuntimeError:
                        thread_id = 'default'
                    
                    # Get cached embeddings for this thread
                    if thread_id not in SEMANTIC_CACHE:
                        SEMANTIC_CACHE[thread_id] = []
                    
                    cached_embeddings = [entry["embedding"] for entry in SEMANTIC_CACHE[thread_id]]
                    
                    # Check similarity
                    threshold = getattr(agent, 'semantic_similarity_threshold', 0.90)
                    is_repetitive, max_sim = check_semantic_repetition(
                        current_embedding, 
                        cached_embeddings, 
                        threshold
                    )
                    
                    # Log similarity for monitoring
                    print(f"[DEBUG] Semantic check: similarity={max_sim:.3f}, threshold={threshold:.3f}, regenerated={is_repetitive}")
                    
                    if is_repetitive:
                        # Regenerate with constraint
                        constraint = f"""
IMPORTANT: Your previous questions were semantically similar (similarity: {max_sim:.2f}).
Generate a question that uses a different reasoning approach and resolution strategy.
Do not reuse the same control objective or decision logic.
"""
                        
                        # Append constraint to prompt
                        try:
                            # Modify api_params for regeneration
                            api_params["messages"][1]["content"] = prompt + "\n\n" + constraint
                            
                            response = _get_openai_client().chat.completions.create(**api_params)
                            raw_response = response.choices[0].message.content.strip()
                            processed, _ = post_process_response(raw_response, agent)
                            
                            # Regenerate embedding for new response
                            new_signature = extract_question_signature(processed)
                            if new_signature:
                                current_embedding = generate_signature_embedding(new_signature)
                        except Exception as e:
                            print(f"[WARN] Semantic retry failed: {e}")
                            pass  # Keep first attempt
                    
                    # Store embedding in cache (limit to last N)
                    max_depth = getattr(agent, 'semantic_history_depth', 5)
                    SEMANTIC_CACHE[thread_id].append({
                        "embedding": current_embedding,
                        "timestamp": datetime.now().isoformat()
                    })
                    
                    # Trim cache to max depth
                    if len(SEMANTIC_CACHE[thread_id]) > max_depth:
                        SEMANTIC_CACHE[thread_id] = SEMANTIC_CACHE[thread_id][-max_depth:]
        
        # Store blueprint after successful generation (only for CISSP mode)
        if agent and hasattr(agent, 'enable_cissp_mode') and agent.enable_cissp_mode:
            from app.utils.reasoning_controller import store_blueprint
            try:
                thread_id = getattr(g, 'thread_id', 'default')
            except RuntimeError:
                thread_id = 'default'
            try:
                blueprint = getattr(g, 'current_blueprint', None)
            except RuntimeError:
                blueprint = None
            if blueprint:
                store_blueprint(thread_id, blueprint, agent.blueprint_history_depth)
        
        return processed


def _generate_with_gemini(message_body, history=None, agent=None, skip_post_processing=False):
    """
    Generate reply using Google Gemini API.
    """
    from app.utils.gemini_client import GeminiClient
    
    # SECURITY: Already checked in generate_reply
    if not agent:
        print("🚫 SECURITY: No agent specified - denying reply generation")
        return "🚫 ACCESS DENIED: No agent specified. Please select an agent to generate a reply."
    
    # Use agent-specific personality and style
    personality = agent.personality or DEFAULT_CONFIG["personality"]
    style = agent.style or DEFAULT_CONFIG["style"]
    
    # Automatically inject agent identity into the system message
    agent_identity = f"You are {agent.name}, an AI assistant. "
    system_message = agent_identity + personality + "\n" + style

    # Blueprint generation for CISSP mode
    if agent and hasattr(agent, 'enable_cissp_mode') and agent.enable_cissp_mode:
        from app.utils.reasoning_controller import select_blueprint, build_blueprint_constraint
        
        try:
            thread_id = getattr(g, 'thread_id', 'default')
        except RuntimeError:
            thread_id = 'default'
        blueprint = select_blueprint(thread_id, message_body, agent.blueprint_history_depth)
        
        # Store in request context for retrieval function to access (if in request context)
        try:
            g.current_blueprint = blueprint
        except RuntimeError:
            pass
        
        # Build constraint text
        blueprint_constraint = build_blueprint_constraint(blueprint)
        
        # Store constraint for prompt injection (if in request context)
        try:
            g.blueprint_constraint = blueprint_constraint
        except RuntimeError:
            pass

    prompt = build_prompt(message_body, history=history, agent=agent)
    
    # SECURITY: If no knowledge base access was granted, block the reply
    if not agent and "KNOWLEDGE BASE INFORMATION:" in prompt and "---" in prompt:
        kb_content = prompt.split("KNOWLEDGE BASE INFORMATION:")[1].split("SCHEDULE INFORMATION:")[0]
        if kb_content.strip() == "---":
            print("🚫 SECURITY: No knowledge base access - blocking reply generation")
            return "🚫 ACCESS DENIED: No knowledge base access granted. Please select an agent with proper permissions."
    
    try:
        client = GeminiClient()
        
        # Prepare messages for Gemini
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt}
        ]
        
        # Use provider_model if set, otherwise fall back to a default
        model = agent.provider_model or "gemini-2.5-flash"
        
        # Call Gemini API
        response = client.generate_content(
            model=model,
            messages=messages,
            temperature=agent.temperature if agent.temperature is not None else 0.9,
            max_tokens=agent.max_output_tokens or agent.max_tokens or 1000
        )
        
        raw_response = response.text
        
        if skip_post_processing:
            return raw_response
        
        processed, validation_ok = post_process_response(raw_response, agent)
        
        # If validation failed and agent has validation rules, retry once
        if not validation_ok and agent.post_processing_rules.get("validation"):
            try:
                # Regenerate with same parameters
                response = client.generate_content(
                    model=model,
                    messages=messages,
                    temperature=agent.temperature if agent.temperature is not None else 0.9,
                    max_tokens=agent.max_output_tokens or agent.max_tokens or 1000
                )
                raw_response = response.text
                processed, _ = post_process_response(raw_response, agent)
            except Exception:
                # If retry fails, return first attempt
                pass
        
        # Semantic repetition check (if enabled for agent)
        if (agent and 
            hasattr(agent, 'enable_semantic_detection') and 
            agent.enable_semantic_detection):
            
            # Extract question signature
            signature = extract_question_signature(processed)
            
            if signature:
                # Generate embedding
                current_embedding = generate_signature_embedding(signature)
                
                if current_embedding is not None:
                    # Get thread ID from request context (if available)
                    try:
                        thread_id = getattr(g, 'thread_id', 'default')
                    except RuntimeError:
                        thread_id = 'default'
                    
                    # Get cached embeddings for this thread
                    if thread_id not in SEMANTIC_CACHE:
                        SEMANTIC_CACHE[thread_id] = []
                    
                    cached_embeddings = [entry["embedding"] for entry in SEMANTIC_CACHE[thread_id]]
                    
                    # Check similarity
                    threshold = getattr(agent, 'semantic_similarity_threshold', 0.90)
                    is_repetitive, max_sim = check_semantic_repetition(
                        current_embedding, 
                        cached_embeddings, 
                        threshold
                    )
                    
                    # Log similarity for monitoring
                    print(f"[DEBUG] Semantic check: similarity={max_sim:.3f}, threshold={threshold:.3f}, regenerated={is_repetitive}")
                    
                    if is_repetitive:
                        # Regenerate with constraint
                        constraint = f"""
IMPORTANT: Your previous questions were semantically similar (similarity: {max_sim:.2f}).
Generate a question that uses a different reasoning approach and resolution strategy.
Do not reuse the same control objective or decision logic.
"""
                        
                        # Append constraint to prompt
                        try:
                            messages[1]["content"] = prompt + "\n\n" + constraint
                            
                            response = client.generate_content(
                                model=model,
                                messages=messages,
                                temperature=agent.temperature if agent.temperature is not None else 0.9,
                                max_tokens=agent.max_output_tokens or agent.max_tokens or 1000
                            )
                            raw_response = response.text
                            processed, _ = post_process_response(raw_response, agent)
                            
                            # Regenerate embedding for new response
                            new_signature = extract_question_signature(processed)
                            if new_signature:
                                current_embedding = generate_signature_embedding(new_signature)
                        except Exception as e:
                            print(f"[WARN] Semantic retry failed: {e}")
                            pass  # Keep first attempt
                    
                    # Store embedding in cache (limit to last N)
                    max_depth = getattr(agent, 'semantic_history_depth', 5)
                    SEMANTIC_CACHE[thread_id].append({
                        "embedding": current_embedding,
                        "timestamp": datetime.now().isoformat()
                    })
                    
                    # Trim cache to max depth
                    if len(SEMANTIC_CACHE[thread_id]) > max_depth:
                        SEMANTIC_CACHE[thread_id] = SEMANTIC_CACHE[thread_id][-max_depth:]
        
        # Store blueprint after successful generation (only for CISSP mode)
        if agent and hasattr(agent, 'enable_cissp_mode') and agent.enable_cissp_mode:
            from app.utils.reasoning_controller import store_blueprint
            try:
                thread_id = getattr(g, 'thread_id', 'default')
            except RuntimeError:
                thread_id = 'default'
            try:
                blueprint = getattr(g, 'current_blueprint', None)
            except RuntimeError:
                blueprint = None
            if blueprint:
                store_blueprint(thread_id, blueprint, agent.blueprint_history_depth)
        
        return processed
        
    except Exception as e:
        print(f"[ERROR] Gemini generation error: {e}")
        return f"Error generating response with Gemini: {str(e)}"


def generate_quiz_questions_for_agent(agent, count=5):
    """
    Generate multiple-choice questions using the agent's KB and configuration.
    Returns structured JSON with questions, options, correct answers, and explanations.
    
    Args:
        agent: Agent object with configuration
        count: Number of questions to generate
        
    Returns:
        List of question dictionaries
    """
    import json
    import uuid
    
    # Build specialized quiz generation prompt
    quiz_prompt = f"""Generate exactly {count} multiple-choice questions based on your knowledge base.

For each question:
1. Create a scenario-based question testing high-level understanding
2. Provide exactly 4 options (A, B, C, D)
3. One option must be the BEST answer
4. Include a 2-3 sentence explanation of why the correct answer is best

Return ONLY valid JSON in this exact format:
[
  {{
    "question": "Question text here",
    "options": {{
      "A": "Option A text",
      "B": "Option B text",
      "C": "Option C text",
      "D": "Option D text"
    }},
    "correct": "A",
    "explanation": "Explanation of why A is the best answer"
  }}
]

Do not include any text before or after the JSON array."""

    try:
        # Temporarily override token limits for quiz generation
        # Each question ~300-400 tokens, so 5 questions need ~2000 tokens minimum
        original_max_tokens = agent.max_tokens
        original_max_completion_tokens = agent.max_completion_tokens
        original_max_output_tokens = agent.max_output_tokens
        
        # Set high enough limit for multiple questions
        required_tokens = count * 400 + 200  # ~400 tokens per question + buffer
        agent.max_tokens = max(required_tokens, 2500)
        agent.max_completion_tokens = max(required_tokens, 2500)
        agent.max_output_tokens = max(required_tokens, 2500)
        
        try:
            # Generate questions using the agent's reply generation
            # Skip post-processing to get raw JSON output
            response = generate_reply(quiz_prompt, history=None, agent=agent, skip_post_processing=True)
        finally:
            # Always restore original token limits
            agent.max_tokens = original_max_tokens
            agent.max_completion_tokens = original_max_completion_tokens
            agent.max_output_tokens = original_max_output_tokens
        
        # Try to extract JSON from the response
        # Sometimes the model includes markdown code blocks
        json_start = response.find('[')
        json_end = response.rfind(']') + 1
        
        if json_start == -1 or json_end == 0:
            raise ValueError("No JSON array found in response")
        
        json_str = response[json_start:json_end]
        questions_data = json.loads(json_str)
        
        # Add unique IDs to each question
        questions = []
        for q in questions_data:
            questions.append({
                "question_id": str(uuid.uuid4()),
                "question_text": q.get("question", ""),
                "options": q.get("options", {}),
                "correct_answer": q.get("correct", ""),
                "explanation": q.get("explanation", "")
            })
        
        return questions
        
    except json.JSONDecodeError as e:
        print(f"[WARN] JSON parsing error: {e}")
        print(f"Response was: {response[:500]}")
        # Return a fallback error structure
        return [{
            "question_id": str(uuid.uuid4()),
            "question_text": "Unable to generate questions at this time.",
            "options": {
                "A": "Please try again",
                "B": "Check agent configuration",
                "C": "Verify knowledge base",
                "D": "Contact support"
            },
            "correct_answer": "A",
            "explanation": "There was an error generating questions. Please try again or check the agent configuration."
        }]
    except Exception as e:
        print(f"[WARN] Quiz generation error: {e}")
        import traceback
        traceback.print_exc()
        return [{
            "question_id": str(uuid.uuid4()),
            "question_text": f"Error: {str(e)}",
            "options": {
                "A": "Try again",
                "B": "Check logs",
                "C": "Verify setup",
                "D": "Contact admin"
            },
            "correct_answer": "A",
            "explanation": f"An error occurred: {str(e)}"
        }]


# Manual test
if __name__ == "__main__":
    sample_message = """Hi, I'm interested in your services. I live in Long Island.
I don't have a high school diploma—am I still eligible?
Also how long is the program?"""
    
    reply = generate_reply(sample_message)
    print("📩 Suggested reply:\n")
    print(reply)
