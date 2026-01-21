"""
Migration script to add provider fields to existing agents and KBs.
Run once after deployment.
"""
import sys
import os

# Add project root to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

def migrate_agents():
    """Set provider='openai' for all existing agents"""
    from app.models.agent import agent_manager
    agents = agent_manager.get_all_agents()
    
    migrated_count = 0
    for agent in agents:
        if not hasattr(agent, 'provider') or not agent.provider:
            # Default to OpenAI provider with current model
            agent_manager.update_agent(
                agent.agent_id, 
                provider="openai", 
                provider_model=getattr(agent, 'model', 'gpt-5.2')
            )
            migrated_count += 1
    
    print(f"[OK] Migrated {migrated_count} agents to OpenAI provider")
    print(f"   Total agents: {len(agents)}")

def migrate_knowledge_bases():
    """Set embedding_provider='openai' for all existing KBs"""
    from app.config.knowledge_config import load_knowledge_config, save_knowledge_config
    
    config = load_knowledge_config()
    kbs = config.get("knowledge_bases", [])
    
    migrated_count = 0
    for kb in kbs:
        if "embedding_provider" not in kb:
            kb["embedding_provider"] = "openai"
            kb["embedding_model"] = "text-embedding-3-large"
            migrated_count += 1
    
    save_knowledge_config(config)
    print(f"[OK] Migrated {migrated_count} knowledge bases to OpenAI embeddings")
    print(f"   Total knowledge bases: {len(kbs)}")

if __name__ == "__main__":
    print("[*] Starting provider migration...")
    print("=" * 50)
    migrate_agents()
    print()
    migrate_knowledge_bases()
    print("=" * 50)
    print("[*] Migration complete!")
