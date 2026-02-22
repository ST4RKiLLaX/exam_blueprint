"""
Secure Access Control Module
Implements strict implicit deny for knowledge base access.
Agents can ONLY access knowledge bases they're explicitly assigned to.
"""

from app.config.knowledge_config import get_knowledge_bases_for_agent

def secure_knowledge_base_access(agent, requested_kb_ids=None):
    """
    STRICT SECURITY: Implicit deny - agents can ONLY access explicitly assigned knowledge bases.
    No fallbacks, no bypasses, no exceptions.
    
    Args:
        agent: The agent requesting access
        requested_kb_ids: Optional list of KB IDs to check (if None, uses agent's assigned KBs)
    
    Returns:
        List of knowledge bases the agent is authorized to access
    """
    if not agent:
        print("🚫 SECURITY: No agent specified - denying all access")
        return []
    
    if not agent.knowledge_bases:
        print(f"🚫 SECURITY: Agent '{agent.name}' has no assigned knowledge bases - denying all access")
        return []
    
    # If specific KB IDs requested, validate they're all assigned to the agent
    if requested_kb_ids:
        unauthorized_kbs = [kb_id for kb_id in requested_kb_ids if kb_id not in agent.knowledge_bases]
        if unauthorized_kbs:
            print(f"🚫 SECURITY: Agent '{agent.name}' attempted to access unauthorized KBs: {unauthorized_kbs}")
            print(f"   Authorized KBs: {agent.knowledge_bases}")
            # Return only authorized KBs from the requested list
            authorized_kbs = [kb_id for kb_id in requested_kb_ids if kb_id in agent.knowledge_bases]
            return get_knowledge_bases_for_agent(agent.agent_id, authorized_kbs)
    
    # Return only the agent's explicitly assigned knowledge bases
    authorized_kbs = get_knowledge_bases_for_agent(agent.agent_id, agent.knowledge_bases)
    print(f"🔒 SECURITY: Agent '{agent.name}' accessing authorized KBs: {[kb['id'] for kb in authorized_kbs]}")
    return authorized_kbs

def secure_search_all_knowledge_bases(query, top_k=3, agent=None):
    """
    SECURE SEARCH: Implicit deny - agents can ONLY access their assigned knowledge bases.
    """
    if agent:
        # STRICT: Only agent-assigned knowledge bases
        knowledge_bases = secure_knowledge_base_access(agent)
    else:
        # No agent = no access (implicit deny)
        print("🚫 SECURITY: No agent specified - denying all knowledge base access")
        return []
    
    from app.utils.knowledge_processor import search_knowledge_base
    
    all_results = []
    for kb in knowledge_bases:
        kb_results = search_knowledge_base(kb["id"], query, top_k)
        if kb_results:
            all_results.extend(kb_results)
    
    return all_results

def secure_search_agent_knowledge_bases(query, agent, top_k=3):
    """
    SECURE SEARCH: Implicit deny - agents can ONLY access their assigned knowledge bases.
    """
    if not agent:
        print("🚫 SECURITY: No agent specified - denying all knowledge base access")
        return []
    
    # STRICT: Only agent-assigned knowledge bases
    knowledge_bases = secure_knowledge_base_access(agent)
    
    from app.utils.knowledge_processor import search_knowledge_base
    
    all_results = []
    for kb in knowledge_bases:
        kb_results = search_knowledge_base(kb["id"], query, top_k)
        if kb_results:
            all_results.extend(kb_results)
    
    return all_results

