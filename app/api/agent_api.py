from typing import List, Optional, Dict
from app.models.agent import Agent, agent_manager


class AgentAPI:
    """API layer for agent management operations"""
    
    @staticmethod
    def create_agent(name: str, personality: str = "", style: str = "", 
                    prompt: str = "", formatting: str = "", knowledge_bases: List[str] = None,
                    provider: str = "openai", provider_model: str = "gpt-5.2",
                    model: str = "gpt-5.2", temperature: float = 0.9,
                    frequency_penalty: float = 0.7, presence_penalty: float = 0.5,
                    max_tokens: int = 1000, top_p: float = None,
                    max_completion_tokens: int = None, max_output_tokens: int = None,
                    reasoning_effort: str = None, verbosity: str = None,
                    stop: List[str] = None, max_knowledge_chunks: int = 7,
                    min_similarity_threshold: float = 1.0, 
                    conversation_history_tokens: int = 1000,
                    post_processing_rules: Dict = None,
                    enable_semantic_detection: bool = False,
                    semantic_similarity_threshold: float = 0.90,
                    semantic_history_depth: int = 5,
                    exam_profile_id: str = None,
                    blueprint_history_depth: int = 8) -> Dict:
        """Create a new agent and return result"""
        try:
            if not name.strip():
                return {"success": False, "error": "Agent name is required"}
            
            agent = agent_manager.create_agent(
                name=name.strip(),
                personality=personality,
                style=style,
                prompt=prompt,
                formatting=formatting,
                knowledge_bases=knowledge_bases or [],
                provider=provider,
                provider_model=provider_model,
                model=model,
                temperature=temperature,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
                max_tokens=max_tokens,
                top_p=top_p,
                max_completion_tokens=max_completion_tokens,
                max_output_tokens=max_output_tokens,
                reasoning_effort=reasoning_effort,
                verbosity=verbosity,
                stop=stop,
                max_knowledge_chunks=max_knowledge_chunks,
                min_similarity_threshold=min_similarity_threshold,
                conversation_history_tokens=conversation_history_tokens,
                post_processing_rules=post_processing_rules,
                enable_semantic_detection=enable_semantic_detection,
                semantic_similarity_threshold=semantic_similarity_threshold,
                semantic_history_depth=semantic_history_depth,
                exam_profile_id=exam_profile_id,
                blueprint_history_depth=blueprint_history_depth
            )
            
            return {
                "success": True, 
                "agent": agent.to_dict(),
                "message": f"Agent '{name}' created successfully"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def get_agent(agent_id: str) -> Dict:
        """Get agent by ID"""
        try:
            agent = agent_manager.get_agent(agent_id)
            if agent:
                return {"success": True, "agent": agent.to_dict()}
            else:
                return {"success": False, "error": "Agent not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def get_all_agents() -> Dict:
        """Get all agents"""
        try:
            agents = agent_manager.get_all_agents()
            return {
                "success": True, 
                "agents": [agent.to_dict() for agent in agents],
                "count": len(agents)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def get_active_agents() -> Dict:
        """Get all active agents"""
        try:
            agents = agent_manager.get_active_agents()
            return {
                "success": True, 
                "agents": [agent.to_dict() for agent in agents],
                "count": len(agents)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def update_agent(agent_id: str, **kwargs) -> Dict:
        """Update an agent"""
        try:
            # Validate required fields only - None is valid for optional parameters
            if "name" in kwargs and kwargs["name"] is not None and not kwargs["name"].strip():
                return {"success": False, "error": "Agent name cannot be empty"}
            
            success = agent_manager.update_agent(agent_id, **kwargs)
            if success:
                agent = agent_manager.get_agent(agent_id)
                return {
                    "success": True, 
                    "agent": agent.to_dict(),
                    "message": "Agent updated successfully"
                }
            else:
                return {"success": False, "error": "Agent not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def delete_agent(agent_id: str) -> Dict:
        """Delete an agent"""
        try:
            # Check if this is the last active agent
            active_agents = agent_manager.get_active_agents()
            agent_to_delete = agent_manager.get_agent(agent_id)
            
            if not agent_to_delete:
                return {"success": False, "error": "Agent not found"}
            
            # Prevent deletion of the last active agent
            if (len(active_agents) <= 1 and 
                agent_to_delete.status == "active"):
                return {
                    "success": False, 
                    "error": "Cannot delete the last active agent. Create another agent first."
                }
            
            success = agent_manager.delete_agent(agent_id)
            if success:
                return {
                    "success": True, 
                    "message": f"Agent '{agent_to_delete.name}' deleted successfully"
                }
            else:
                return {"success": False, "error": "Failed to delete agent"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def activate_agent(agent_id: str) -> Dict:
        """Activate an agent"""
        return AgentAPI.update_agent(agent_id, status="active")
    
    @staticmethod
    def deactivate_agent(agent_id: str) -> Dict:
        """Deactivate an agent"""
        return AgentAPI.update_agent(agent_id, status="inactive")
    
    @staticmethod
    def clone_agent(agent_id: str, new_name: str) -> Dict:
        """Clone an existing agent with a new name"""
        try:
            original_agent = agent_manager.get_agent(agent_id)
            if not original_agent:
                return {"success": False, "error": "Original agent not found"}
            
            if not new_name.strip():
                return {"success": False, "error": "New agent name is required"}
            
            # Create new agent with same configuration
            new_agent = agent_manager.create_agent(
                name=new_name.strip(),
                personality=original_agent.personality,
                style=original_agent.style,
                prompt=original_agent.prompt,
                formatting=original_agent.formatting,
                knowledge_bases=original_agent.knowledge_bases.copy(),
                model=original_agent.model,
                temperature=original_agent.temperature,
                frequency_penalty=original_agent.frequency_penalty,
                presence_penalty=original_agent.presence_penalty,
                max_tokens=original_agent.max_tokens,
                top_p=original_agent.top_p,
                max_completion_tokens=original_agent.max_completion_tokens,
                max_output_tokens=original_agent.max_output_tokens,
                reasoning_effort=original_agent.reasoning_effort,
                verbosity=original_agent.verbosity,
                stop=original_agent.stop
            )
            
            return {
                "success": True, 
                "agent": new_agent.to_dict(),
                "message": f"Agent cloned as '{new_name}' successfully"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
