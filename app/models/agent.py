import json
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional

class Agent:
    """Represents an AI agent with its configuration and metadata"""
    
    def __init__(self, agent_id: str = None, name: str = "", personality: str = "", 
                 style: str = "", prompt: str = "", status: str = "active", 
                 created_at: str = None, updated_at: str = None, 
                 knowledge_bases: List[str] = None):
        self.agent_id = agent_id or str(uuid.uuid4())
        self.name = name
        self.personality = personality
        self.style = style
        self.prompt = prompt
        self.status = status  # active, inactive, archived
        self.created_at = created_at or datetime.now().isoformat()
        self.updated_at = updated_at or datetime.now().isoformat()
        self.knowledge_bases = knowledge_bases or []
    
    def to_dict(self) -> Dict:
        """Convert agent to dictionary for JSON serialization"""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "personality": self.personality,
            "style": self.style,
            "prompt": self.prompt,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "knowledge_bases": self.knowledge_bases
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Agent':
        """Create agent from dictionary"""
        # Filter out legacy fields that are no longer supported
        filtered_data = {k: v for k, v in data.items() if k != 'email_accounts'}
        return cls(**filtered_data)
    
    def update(self, **kwargs):
        """Update agent properties and set updated_at timestamp"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.updated_at = datetime.now().isoformat()


class AgentManager:
    """Manages multiple AI agents"""
    
    def __init__(self, storage_path: str = None):
        self.storage_path = storage_path or os.path.join(
            os.path.dirname(__file__), "..", "config", "agents.json"
        )
        self._agents = {}
        self.load_agents()
    
    def load_agents(self):
        """Load agents from storage"""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._agents = {
                        agent_id: Agent.from_dict(agent_data) 
                        for agent_id, agent_data in data.get("agents", {}).items()
                    }
            except (json.JSONDecodeError, FileNotFoundError):
                self._agents = {}
        
        # If no agents exist, create a default one from current config
        if not self._agents:
            self._create_default_agent()
    
    def _create_default_agent(self):
        """Create default agent with basic configuration"""
        default_agent = Agent(
            name="AI Assistant",
            personality="You are a helpful AI assistant.",
            style="Use a professional and friendly tone.",
            prompt="Please provide helpful and accurate responses.",
            status="active"
        )
        self._agents[default_agent.agent_id] = default_agent
        self.save_agents()
    
    def save_agents(self):
        """Save agents to storage"""
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        data = {
            "agents": {
                agent_id: agent.to_dict() 
                for agent_id, agent in self._agents.items()
            }
        }
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def create_agent(self, name: str, personality: str = "", style: str = "", 
                    prompt: str = "", knowledge_bases: List[str] = None) -> Agent:
        """Create a new agent"""
        agent = Agent(
            name=name,
            personality=personality,
            style=style,
            prompt=prompt,
            knowledge_bases=knowledge_bases or []
        )
        self._agents[agent.agent_id] = agent
        self.save_agents()
        return agent
    
    def get_agent(self, agent_id: str) -> Optional[Agent]:
        """Get agent by ID"""
        return self._agents.get(agent_id)
    
    def get_all_agents(self) -> List[Agent]:
        """Get all agents"""
        return list(self._agents.values())
    
    def get_active_agents(self) -> List[Agent]:
        """Get all active agents"""
        return [agent for agent in self._agents.values() if agent.status == "active"]
    
    def update_agent(self, agent_id: str, **kwargs) -> bool:
        """Update an agent"""
        agent = self._agents.get(agent_id)
        if agent:
            agent.update(**kwargs)
            self.save_agents()
            return True
        return False
    
    def delete_agent(self, agent_id: str) -> bool:
        """Delete an agent"""
        if agent_id in self._agents:
            del self._agents[agent_id]
            self.save_agents()
            return True
        return False
    
    def get_default_agent(self) -> Optional[Agent]:
        """Get the first active agent as default"""
        active_agents = self.get_active_agents()
        return active_agents[0] if active_agents else None


# Global agent manager instance
agent_manager = AgentManager()
