import json
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any

class Agent:
    """Represents an AI agent with its configuration and metadata"""
    
    def __init__(self, agent_id: str = None, name: str = "", personality: str = "", 
                 style: str = "", prompt: str = "", formatting: str = "", status: str = "active", 
                 created_at: str = None, updated_at: str = None, 
                 knowledge_bases: List[str] = None,
                 # Provider selection
                 provider: str = "openai",
                 provider_model: str = "gpt-5.2",
                 provider_key_name: str = "default",
                 # Model parameters with recommended defaults for question generation
                 model: str = "gpt-5.2",  # Kept for backward compatibility
                 temperature: float = 0.9,
                 frequency_penalty: float = 0.7,
                 presence_penalty: float = 0.5,
                 max_tokens: int = 1000,
                 top_p: float = None,
                 # Model-specific parameters
                 max_completion_tokens: int = None,
                 max_output_tokens: int = None,
                 reasoning_effort: str = None,
                 verbosity: str = None,
                 stop: List[str] = None,
                 # Knowledge base search parameters
                 max_knowledge_chunks: int = 7,
                 min_similarity_threshold: float = 1.0,
                 conversation_history_tokens: int = 1000,
                 # Post-processing rules
                 post_processing_rules: Dict = None,
                 # Semantic repetition detection
                 enable_semantic_detection: bool = False,
                 semantic_similarity_threshold: float = 0.90,
                 semantic_history_depth: int = 5,
                 hot_topics_mode: str = "priority",
                 # Exam profile (replaces CISSP-specific mode)
                 exam_profile_id: Optional[str] = None,
                 # CISSP reasoning controller (deprecated, use exam_profile_id)
                 enable_cissp_mode: bool = True,
                 blueprint_history_depth: int = 8):
        self.agent_id = agent_id or str(uuid.uuid4())
        self.name = name
        self.personality = personality
        self.style = style
        self.prompt = prompt
        self.formatting = formatting
        self.status = status  # active, inactive, archived
        self.created_at = created_at or datetime.now().isoformat()
        self.updated_at = updated_at or datetime.now().isoformat()
        self.knowledge_bases = knowledge_bases or []
        # Provider selection
        self.provider = provider
        self.provider_model = provider_model
        self.provider_key_name = provider_key_name
        # Model parameters (kept for backward compatibility)
        self.model = model
        self.temperature = temperature
        self.frequency_penalty = frequency_penalty
        self.presence_penalty = presence_penalty
        self.max_tokens = max_tokens
        self.top_p = top_p
        # Model-specific parameters
        self.max_completion_tokens = max_completion_tokens
        self.max_output_tokens = max_output_tokens
        self.reasoning_effort = reasoning_effort
        self.verbosity = verbosity
        self.stop = stop
        # Knowledge base search parameters
        self.max_knowledge_chunks = max_knowledge_chunks
        self.min_similarity_threshold = min_similarity_threshold
        self.conversation_history_tokens = conversation_history_tokens
        self.post_processing_rules = post_processing_rules or {}
        self.enable_semantic_detection = enable_semantic_detection
        self.semantic_similarity_threshold = semantic_similarity_threshold
        self.semantic_history_depth = semantic_history_depth
        self.hot_topics_mode = hot_topics_mode
        self.exam_profile_id = exam_profile_id
        self.enable_cissp_mode = enable_cissp_mode
        self.blueprint_history_depth = blueprint_history_depth
    
    def to_dict(self) -> Dict:
        """Convert agent to dictionary for JSON serialization"""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "personality": self.personality,
            "style": self.style,
            "prompt": self.prompt,
            "formatting": self.formatting,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "knowledge_bases": self.knowledge_bases,
            "provider": self.provider,
            "provider_model": self.provider_model,
            "provider_key_name": self.provider_key_name,
            "model": self.model,
            "temperature": self.temperature,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "max_completion_tokens": self.max_completion_tokens,
            "max_output_tokens": self.max_output_tokens,
            "reasoning_effort": self.reasoning_effort,
            "verbosity": self.verbosity,
            "stop": self.stop,
            "max_knowledge_chunks": self.max_knowledge_chunks,
            "min_similarity_threshold": self.min_similarity_threshold,
            "conversation_history_tokens": self.conversation_history_tokens,
            "post_processing_rules": self.post_processing_rules,
            "enable_semantic_detection": self.enable_semantic_detection,
            "semantic_similarity_threshold": self.semantic_similarity_threshold,
            "semantic_history_depth": self.semantic_history_depth,
            "hot_topics_mode": self.hot_topics_mode,
            "exam_profile_id": self.exam_profile_id,
            "enable_cissp_mode": self.enable_cissp_mode,
            "blueprint_history_depth": self.blueprint_history_depth
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Agent':
        """Create agent from dictionary"""
        # Filter out legacy fields that are no longer supported
        filtered_data = {k: v for k, v in data.items() if k != 'email_accounts'}
        
        # Set defaults for new model parameters if missing (migration)
        if 'model' not in filtered_data:
            filtered_data['model'] = "gpt-5.2"
        if 'temperature' not in filtered_data:
            filtered_data['temperature'] = 0.9
        if 'frequency_penalty' not in filtered_data:
            filtered_data['frequency_penalty'] = 0.7
        if 'presence_penalty' not in filtered_data:
            filtered_data['presence_penalty'] = 0.5
        if 'max_tokens' not in filtered_data:
            filtered_data['max_tokens'] = 1000
        if 'top_p' not in filtered_data:
            filtered_data['top_p'] = None
        
        # Set defaults for model-specific parameters (migration)
        if 'max_completion_tokens' not in filtered_data:
            filtered_data['max_completion_tokens'] = None
        if 'max_output_tokens' not in filtered_data:
            filtered_data['max_output_tokens'] = None
        if 'reasoning_effort' not in filtered_data:
            filtered_data['reasoning_effort'] = None
        if 'verbosity' not in filtered_data:
            filtered_data['verbosity'] = None
        if 'stop' not in filtered_data:
            filtered_data['stop'] = None
        
        # Set defaults for knowledge base search parameters (migration)
        if 'max_knowledge_chunks' not in filtered_data:
            filtered_data['max_knowledge_chunks'] = 7
        if 'min_similarity_threshold' not in filtered_data:
            filtered_data['min_similarity_threshold'] = 1.0
        if 'conversation_history_tokens' not in filtered_data:
            filtered_data['conversation_history_tokens'] = 1000
        if 'post_processing_rules' not in filtered_data:
            filtered_data['post_processing_rules'] = {}
        if 'enable_semantic_detection' not in filtered_data:
            filtered_data['enable_semantic_detection'] = False
        if 'semantic_similarity_threshold' not in filtered_data:
            filtered_data['semantic_similarity_threshold'] = 0.90
        if 'semantic_history_depth' not in filtered_data:
            filtered_data['semantic_history_depth'] = 5
        if 'hot_topics_mode' not in filtered_data:
            filtered_data['hot_topics_mode'] = "priority"
        elif filtered_data['hot_topics_mode'] not in {"disabled", "assistive", "priority"}:
            filtered_data['hot_topics_mode'] = "priority"
        
        # Set defaults for CISSP reasoning controller (migration)
        if 'enable_cissp_mode' not in filtered_data:
            filtered_data['enable_cissp_mode'] = True
        if 'blueprint_history_depth' not in filtered_data:
            filtered_data['blueprint_history_depth'] = 8
        
        # Migrate enable_cissp_mode to exam_profile_id (migration)
        if 'exam_profile_id' not in filtered_data:
            # If enable_cissp_mode is True, convert to CISSP profile
            if filtered_data.get('enable_cissp_mode', False):
                filtered_data['exam_profile_id'] = 'cissp_2024'
            else:
                filtered_data['exam_profile_id'] = None
        
        # Set defaults for provider fields (migration)
        if 'provider' not in filtered_data:
            filtered_data['provider'] = "openai"
        if 'provider_model' not in filtered_data:
            # Use existing model field if available, else default to gpt-5.2
            filtered_data['provider_model'] = filtered_data.get('model', 'gpt-5.2')
        if 'provider_key_name' not in filtered_data:
            filtered_data['provider_key_name'] = "default"
            
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
        self._last_loaded_mtime = None
        self.load_agents()
    
    def load_agents(self):
        """Load agents from storage"""
        needs_save = False
        if os.path.exists(self.storage_path):
            try:
                self._last_loaded_mtime = os.path.getmtime(self.storage_path)
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._agents = {
                        agent_id: Agent.from_dict(agent_data) 
                        for agent_id, agent_data in data.get("agents", {}).items()
                    }
                    # Check if any agent was migrated (from_dict adds defaults)
                    for agent_data in data.get("agents", {}).values():
                        if 'model' not in agent_data:
                            needs_save = True
                            break
            except (json.JSONDecodeError, FileNotFoundError):
                self._agents = {}
                self._last_loaded_mtime = None
        else:
            self._last_loaded_mtime = None
        
        # If no agents exist, create a default one from current config
        if not self._agents:
            self._create_default_agent()
        elif needs_save:
            # Save migrated agents with new defaults
            print("📦 Migrating agents to include model parameters...")
            self.save_agents()
    
    def _create_default_agent(self):
        """Create default agent with basic configuration"""
        default_agent = Agent(
            name="AI Assistant",
            personality="You are a helpful AI assistant.",
            style="Use a professional and friendly tone.",
            prompt="Please provide helpful and accurate responses.",
            formatting="Use clear, organized formatting with appropriate spacing and structure.",
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
        self._last_loaded_mtime = os.path.getmtime(self.storage_path)

    def _sync_from_disk_if_changed(self):
        """
        Reload agents from disk when another process modifies storage.

        This avoids stale in-memory state when running with multiple workers
        or the Flask debug reloader.
        """
        if not os.path.exists(self.storage_path):
            return
        try:
            current_mtime = os.path.getmtime(self.storage_path)
        except OSError:
            return
        if self._last_loaded_mtime is None or current_mtime > self._last_loaded_mtime:
            self.load_agents()
    
    def create_agent(self, name: str, personality: str = "", style: str = "", 
                    prompt: str = "", formatting: str = "", knowledge_bases: List[str] = None,
                    provider: str = "openai", provider_model: str = "gpt-5.2",
                    provider_key_name: str = "default",
                    model: str = "gpt-5.2", temperature: float = 0.9,
                    frequency_penalty: float = 0.7, presence_penalty: float = 0.5,
                    max_tokens: int = 1000, top_p: float = None,
                    max_completion_tokens: int = None, max_output_tokens: int = None,
                    reasoning_effort: str = None, verbosity: str = None,
                    stop: List[str] = None, max_knowledge_chunks: int = 7,
                    min_similarity_threshold: float = 1.0, conversation_history_tokens: int = 1000,
                    post_processing_rules: Dict = None,
                    enable_semantic_detection: bool = False,
                    semantic_similarity_threshold: float = 0.90,
                    semantic_history_depth: int = 5,
                    hot_topics_mode: str = "priority",
                    exam_profile_id: str = None,
                    blueprint_history_depth: int = 8) -> Agent:
        """Create a new agent"""
        self._sync_from_disk_if_changed()
        agent = Agent(
            name=name,
            personality=personality,
            style=style,
            prompt=prompt,
            formatting=formatting,
            knowledge_bases=knowledge_bases or [],
            provider=provider,
            provider_model=provider_model,
            provider_key_name=provider_key_name,
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
            hot_topics_mode=hot_topics_mode,
            exam_profile_id=exam_profile_id,
            blueprint_history_depth=blueprint_history_depth
        )
        self._agents[agent.agent_id] = agent
        self.save_agents()
        return agent
    
    def get_agent(self, agent_id: str) -> Optional[Agent]:
        """Get agent by ID"""
        self._sync_from_disk_if_changed()
        return self._agents.get(agent_id)
    
    def get_all_agents(self) -> List[Agent]:
        """Get all agents"""
        self._sync_from_disk_if_changed()
        return list(self._agents.values())
    
    def get_active_agents(self) -> List[Agent]:
        """Get all active agents"""
        self._sync_from_disk_if_changed()
        return [agent for agent in self._agents.values() if agent.status == "active"]
    
    def update_agent(self, agent_id: str, **kwargs) -> bool:
        """Update an agent"""
        self._sync_from_disk_if_changed()
        agent = self._agents.get(agent_id)
        if agent:
            agent.update(**kwargs)
            self.save_agents()
            return True
        return False
    
    def delete_agent(self, agent_id: str) -> bool:
        """Delete an agent"""
        self._sync_from_disk_if_changed()
        if agent_id in self._agents:
            del self._agents[agent_id]
            self.save_agents()
            return True
        return False
    
    def export_agent(self, agent_id: str) -> tuple[bool, str, Optional[Dict]]:
        """
        Export an agent as JSON with metadata about KB references.
        
        Args:
            agent_id: Agent identifier to export
            
        Returns:
            Tuple of (success, message, agent_data)
        """
        agent = self.get_agent(agent_id)
        if not agent:
            return False, "Agent not found", None
        
        # Get agent dict
        agent_data = agent.to_dict()
        
        # Add metadata with KB titles for user reference
        from app.config.knowledge_config import load_knowledge_config
        kb_config = load_knowledge_config()
        kb_titles = []
        for kb_id in agent.knowledge_bases:
            for kb in kb_config.get("knowledge_bases", []):
                if kb.get("id") == kb_id:
                    kb_titles.append(kb.get("title", "Unknown"))
                    break
        
        agent_data["_metadata"] = {
            "kb_titles": kb_titles,
            "export_timestamp": datetime.now().isoformat(),
            "export_version": "1.0"
        }
        
        return True, "Agent exported successfully", agent_data
    
    def import_agent(self, agent_data: Dict[str, Any]) -> tuple[bool, str, List[str]]:
        """
        Import an agent from JSON, creating a new copy.
        Returns (success, message, warnings_list)
        
        Args:
            agent_data: Agent dictionary to import
            
        Returns:
            Tuple of (success, message, warnings)
        """
        warnings = []
        self._sync_from_disk_if_changed()
        
        # Remove metadata if present
        agent_data.pop("_metadata", None)
        
        # Validate required fields
        required_fields = ["name", "personality", "style", "prompt"]
        for field in required_fields:
            if field not in agent_data:
                return False, f"Missing required field: {field}", []
        
        # Validate and handle exam_profile_id
        exam_profile_id = agent_data.get("exam_profile_id")
        if exam_profile_id:
            from app.config.exam_profile_config import profile_exists
            if not profile_exists(exam_profile_id):
                warnings.append(f"Exam profile '{exam_profile_id}' not found - set to None")
                agent_data["exam_profile_id"] = None
        
        # Clear knowledge base references
        kb_count = len(agent_data.get("knowledge_bases", []))
        if kb_count > 0:
            warnings.append(f"{kb_count} KB reference(s) cleared - reassign in agent settings")
        agent_data["knowledge_bases"] = []
        
        # Remove old IDs and timestamps - will be regenerated
        agent_data.pop("agent_id", None)
        agent_data.pop("created_at", None)
        agent_data.pop("updated_at", None)
        
        # Create new agent
        try:
            agent = Agent.from_dict(agent_data)
            self._agents[agent.agent_id] = agent
            self.save_agents()
            return True, "Agent imported successfully", warnings
        except Exception as e:
            return False, f"Failed to create agent: {str(e)}", []
    
    def get_default_agent(self) -> Optional[Agent]:
        """Get the first active agent as default"""
        active_agents = self.get_active_agents()
        return active_agents[0] if active_agents else None


# Global agent manager instance
agent_manager = AgentManager()
