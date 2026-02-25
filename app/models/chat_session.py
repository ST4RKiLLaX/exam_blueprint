import json
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional

class ChatSession:
    """Represents a chat session between a user and an agent"""
    
    def __init__(
        self,
        session_id: str,
        agent_id: str,
        user_id: str = None,
        created_at: str = None,
        messages: List[Dict] = None,
    ):
        self.session_id = session_id
        self.agent_id = agent_id
        self.user_id = user_id
        self.created_at = created_at or datetime.now().isoformat()
        self.messages = messages or []
    
    def add_message(self, role: str, content: str):
        """Add a message to the session"""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
    
    def get_recent_messages(self, limit: int = 10) -> List[Dict]:
        """Get the most recent messages for context"""
        return self.messages[-limit:] if self.messages else []
    
    def to_dict(self) -> Dict:
        """Convert session to dictionary for JSON serialization"""
        return {
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "messages": self.messages
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ChatSession':
        """Create session from dictionary"""
        return cls(**data)

class ChatSessionManager:
    """Manages multiple chat sessions"""
    
    def __init__(self, storage_path: str = None):
        self.storage_path = storage_path or os.path.join(
            os.path.dirname(__file__), "..", "config", "chat_sessions.json"
        )
        self._sessions = {}
        self._last_loaded_mtime = None
        self.load_sessions()
    
    def create_session(self, agent_id: str, user_id: str = None) -> ChatSession:
        """Create a new chat session"""
        self._sync_from_disk_if_changed()
        session_id = str(uuid.uuid4())
        session = ChatSession(session_id, agent_id, user_id=user_id)
        self._sessions[session_id] = session
        self.save_sessions()
        return session
    
    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """Get a chat session by ID"""
        self._sync_from_disk_if_changed()
        return self._sessions.get(session_id)

    def user_can_access(self, session_id: str, user_id: str, is_admin: bool = False) -> bool:
        """Check whether a user can access a session."""
        session = self.get_session(session_id)
        if not session:
            return False
        if is_admin:
            return True
        # Legacy sessions without ownership are intentionally non-shareable.
        if not session.user_id:
            return False
        return session.user_id == str(user_id)
    
    def add_message(self, session_id: str, role: str, content: str):
        """Add a message to a session"""
        self._sync_from_disk_if_changed()
        session = self.get_session(session_id)
        if session:
            session.add_message(role, content)
            self.save_sessions()
    
    def get_chat_history(self, session_id: str, limit: int = 10) -> List[Dict]:
        """Get chat history for a session in the format expected by generate_reply"""
        self._sync_from_disk_if_changed()
        session = self.get_session(session_id)
        if not session:
            return []
        
        # Convert to the format expected by the email agent
        history = []
        for msg in session.get_recent_messages(limit):
            history.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        return history
    
    def cleanup_old_sessions(self, days_old: int = 7):
        """Clean up old sessions to prevent storage bloat"""
        self._sync_from_disk_if_changed()
        cutoff_date = datetime.now().timestamp() - (days_old * 24 * 60 * 60)
        
        sessions_to_remove = []
        for session_id, session in self._sessions.items():
            try:
                session_timestamp = datetime.fromisoformat(session.created_at).timestamp()
                if session_timestamp < cutoff_date:
                    sessions_to_remove.append(session_id)
            except:
                # If we can't parse the date, remove the session
                sessions_to_remove.append(session_id)
        
        for session_id in sessions_to_remove:
            del self._sessions[session_id]
        
        if sessions_to_remove:
            self.save_sessions()
    
    def load_sessions(self):
        """Load sessions from storage"""
        if os.path.exists(self.storage_path):
            try:
                self._last_loaded_mtime = os.path.getmtime(self.storage_path)
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._sessions = {
                        session_id: ChatSession.from_dict(session_data)
                        for session_id, session_data in data.get("sessions", {}).items()
                    }
            except (json.JSONDecodeError, FileNotFoundError):
                self._sessions = {}
                self._last_loaded_mtime = None
        else:
            self._last_loaded_mtime = None
    
    def save_sessions(self):
        """Save sessions to storage"""
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        data = {
            "sessions": {
                session_id: session.to_dict()
                for session_id, session in self._sessions.items()
            }
        }
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self._last_loaded_mtime = os.path.getmtime(self.storage_path)

    def _sync_from_disk_if_changed(self):
        """Reload sessions when another process updates chat_sessions.json."""
        if not os.path.exists(self.storage_path):
            return
        try:
            current_mtime = os.path.getmtime(self.storage_path)
        except OSError:
            return
        if self._last_loaded_mtime is None or current_mtime > self._last_loaded_mtime:
            self.load_sessions()

# Global instance
chat_session_manager = ChatSessionManager()
