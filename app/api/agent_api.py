from typing import List, Optional, Dict
from app.models.agent import Agent, agent_manager


class AgentAPI:
    """API layer for agent management operations"""
    
    @staticmethod
    def create_agent(name: str, personality: str = "", style: str = "", 
                    prompt: str = "", knowledge_bases: List[str] = None) -> Dict:
        """Create a new agent and return result"""
        try:
            if not name.strip():
                return {"success": False, "error": "Agent name is required"}
            
            agent = agent_manager.create_agent(
                name=name.strip(),
                personality=personality,
                style=style,
                prompt=prompt,
                knowledge_bases=knowledge_bases or []
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
            # Remove empty values and clean up data
            update_data = {k: v for k, v in kwargs.items() if v is not None}
            if "name" in update_data and not update_data["name"].strip():
                return {"success": False, "error": "Agent name cannot be empty"}
            
            success = agent_manager.update_agent(agent_id, **update_data)
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
                email_accounts=original_agent.email_accounts.copy(),
                knowledge_bases=original_agent.knowledge_bases.copy()
            )
            
            return {
                "success": True, 
                "agent": new_agent.to_dict(),
                "message": f"Agent cloned as '{new_name}' successfully"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
