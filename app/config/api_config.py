"""
API Key configuration management with secure storage
"""
import json
import os
from datetime import datetime
from cryptography.fernet import Fernet
from typing import Optional, Dict, Any
import base64

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "api_config.json")
KEY_FILE = os.path.join(os.path.dirname(__file__), ".api_key")

def _get_or_create_encryption_key() -> bytes:
    """Get or create encryption key for API key storage"""
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as f:
            return f.read()
    else:
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as f:
            f.write(key)
        return key

def _encrypt_api_key(api_key: str) -> str:
    """Encrypt API key for secure storage"""
    key = _get_or_create_encryption_key()
    fernet = Fernet(key)
    encrypted = fernet.encrypt(api_key.encode())
    return base64.b64encode(encrypted).decode()

def _decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt API key from storage"""
    try:
        key = _get_or_create_encryption_key()
        fernet = Fernet(key)
        encrypted_bytes = base64.b64decode(encrypted_key.encode())
        decrypted = fernet.decrypt(encrypted_bytes)
        return decrypted.decode()
    except Exception:
        return ""

def load_api_config() -> Dict[str, Any]:
    """Load API configuration from file"""
    default_config = {
        "openai_api_key_encrypted": "",
        "api_key_preview": "",
        "last_updated": None,
        "last_tested": None,
        "test_status": "unknown"
    }
    
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                return {**default_config, **config}
    except Exception as e:
        print(f"Error loading API config: {e}")
    
    return default_config

def save_api_config(config: Dict[str, Any]) -> bool:
    """Save API configuration to file"""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving API config: {e}")
        return False

def get_openai_api_key() -> Optional[str]:
    """Get the current OpenAI API key (decrypted)"""
    # First try environment variable (takes precedence)
    env_key = os.getenv("OPENAI_API_KEY")
    if env_key:
        return env_key
    
    # Then try stored encrypted key
    config = load_api_config()
    encrypted_key = config.get("openai_api_key_encrypted")
    if encrypted_key:
        return _decrypt_api_key(encrypted_key)
    
    return None

def set_openai_api_key(api_key: str) -> bool:
    """Set and encrypt the OpenAI API key"""
    try:
        config = load_api_config()
        
        # Encrypt and store the key
        encrypted_key = _encrypt_api_key(api_key)
        
        # Create preview (first 7 chars + "..." + last 4 chars)
        if len(api_key) > 11:
            preview = f"{api_key[:7]}...{api_key[-4:]}"
        else:
            preview = "sk-...****"
        
        config.update({
            "openai_api_key_encrypted": encrypted_key,
            "api_key_preview": preview,
            "last_updated": datetime.now().isoformat(),
            "test_status": "unknown"
        })
        
        return save_api_config(config)
    except Exception as e:
        print(f"Error setting API key: {e}")
        return False

def test_openai_api_key(api_key: Optional[str] = None) -> Dict[str, Any]:
    """Test the OpenAI API key"""
    try:
        from openai import OpenAI
        
        # Use provided key or get current key
        test_key = api_key or get_openai_api_key()
        if not test_key:
            return {"success": False, "error": "No API key configured"}
        
        # Test the key with a simple API call
        client = OpenAI(api_key=test_key)
        
        # Make a minimal test request
        response = client.models.list()
        
        # Update test status in config
        config = load_api_config()
        config.update({
            "last_tested": datetime.now().isoformat(),
            "test_status": "valid"
        })
        save_api_config(config)
        
        return {
            "success": True,
            "message": "API key is valid and working",
            "models_count": len(response.data) if hasattr(response, 'data') else 0
        }
        
    except Exception as e:
        error_msg = str(e)
        
        # Update test status in config
        config = load_api_config()
        config.update({
            "last_tested": datetime.now().isoformat(),
            "test_status": "invalid"
        })
        save_api_config(config)
        
        return {
            "success": False,
            "error": error_msg
        }

def get_api_key_info() -> Dict[str, Any]:
    """Get API key information for display"""
    config = load_api_config()
    
    # Check if we have a key
    has_key = bool(get_openai_api_key())
    
    return {
        "has_key": has_key,
        "preview": config.get("api_key_preview", "Not Set"),
        "last_updated": config.get("last_updated"),
        "last_tested": config.get("last_tested"),
        "test_status": config.get("test_status", "unknown"),
        "source": "Environment Variable" if os.getenv("OPENAI_API_KEY") else "Stored Encrypted"
    }
