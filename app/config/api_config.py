"""
API Key configuration management with secure storage
"""
import json
import os
from datetime import datetime
from cryptography.fernet import Fernet
from typing import Optional, Dict, Any
import base64
import stat

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "api_config.json")
KEY_FILE = os.path.join(os.path.dirname(__file__), "api_encryption.key")
KEY_FILE_MODE = 0o600


def _ensure_key_file_permissions():
    """Best-effort enforcement of restrictive key file permissions."""
    if not os.path.exists(KEY_FILE):
        return
    try:
        current_mode = stat.S_IMODE(os.stat(KEY_FILE).st_mode)
        if current_mode != KEY_FILE_MODE:
            os.chmod(KEY_FILE, KEY_FILE_MODE)
    except Exception as e:
        print(f"[WARN] Could not enforce key file permissions: {e}")

def _get_or_create_encryption_key() -> bytes:
    """Get or create encryption key for API key storage"""
    if os.path.exists(KEY_FILE):
        _ensure_key_file_permissions()
        with open(KEY_FILE, "rb") as f:
            return f.read()
    else:
        key = Fernet.generate_key()
        fd = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, KEY_FILE_MODE)
        with os.fdopen(fd, "wb") as f:
            f.write(key)
        _ensure_key_file_permissions()
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
        "provider_api_keys_encrypted": {},
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


def _migrate_legacy_openai_storage(config: Dict[str, Any]) -> bool:
    """
    Migrate legacy OpenAI storage into unified provider map.
    Returns True if config was changed.
    """
    changed = False
    provider_map = config.get("provider_api_keys_encrypted", {})
    legacy_openai = config.get("openai_api_key_encrypted", "")

    if legacy_openai and "openai" not in provider_map:
        provider_map["openai"] = legacy_openai
        config["provider_api_keys_encrypted"] = provider_map
        changed = True

    # Keep legacy key empty once migrated to enforce single storage source.
    if config.get("openai_api_key_encrypted"):
        config["openai_api_key_encrypted"] = ""
        changed = True

    return changed

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
    """Get the current OpenAI API key from unified encrypted provider storage."""
    config = load_api_config()

    # One-time migration path from legacy field to unified provider map
    if _migrate_legacy_openai_storage(config):
        save_api_config(config)

    encrypted_key = config.get("provider_api_keys_encrypted", {}).get("openai")
    if encrypted_key:
        decrypted = _decrypt_api_key(encrypted_key)
        return decrypted if decrypted else None
    return None

def set_openai_api_key(api_key: str) -> bool:
    """Set and encrypt the OpenAI API key"""
    try:
        config = load_api_config()
        encrypted_key = _encrypt_api_key(api_key)
        provider_map = config.get("provider_api_keys_encrypted", {})
        provider_map["openai"] = encrypted_key
        
        # Create preview (first 7 chars + "..." + last 4 chars)
        if len(api_key) > 11:
            preview = f"{api_key[:7]}...{api_key[-4:]}"
        else:
            preview = "sk-...****"
        
        config.update({
            "provider_api_keys_encrypted": provider_map,
            "openai_api_key_encrypted": "",
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

def delete_openai_api_key() -> bool:
    """Delete the stored OpenAI API key"""
    try:
        config = load_api_config()
        provider_map = config.get("provider_api_keys_encrypted", {})
        if "openai" in provider_map:
            del provider_map["openai"]
        
        # Clear the stored key
        config.update({
            "provider_api_keys_encrypted": provider_map,
            "openai_api_key_encrypted": "",
            "api_key_preview": "Not Set",
            "last_updated": datetime.now().isoformat(),
            "test_status": "deleted"
        })
        
        return save_api_config(config)
    except Exception as e:
        print(f"Error deleting API key: {e}")
        return False

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
        "source": "Stored Encrypted"
    }


def get_provider_api_key_encrypted(provider: str) -> Optional[str]:
    """Get decrypted provider API key stored in encrypted config."""
    config = load_api_config()
    encrypted_keys = config.get("provider_api_keys_encrypted", {})
    encrypted_key = encrypted_keys.get(provider)
    if encrypted_key:
        return _decrypt_api_key(encrypted_key)
    return None


def set_provider_api_key_encrypted(provider: str, api_key: str) -> bool:
    """Set encrypted provider API key in shared encrypted config."""
    try:
        config = load_api_config()
        encrypted_keys = config.get("provider_api_keys_encrypted", {})
        encrypted_keys[provider] = _encrypt_api_key(api_key)
        config["provider_api_keys_encrypted"] = encrypted_keys
        config["last_updated"] = datetime.now().isoformat()
        return save_api_config(config)
    except Exception as e:
        print(f"Error setting encrypted provider API key for {provider}: {e}")
        return False


def delete_provider_api_key_encrypted(provider: str) -> bool:
    """Delete encrypted provider API key from shared encrypted config."""
    try:
        config = load_api_config()
        encrypted_keys = config.get("provider_api_keys_encrypted", {})
        if provider in encrypted_keys:
            del encrypted_keys[provider]
        config["provider_api_keys_encrypted"] = encrypted_keys
        config["last_updated"] = datetime.now().isoformat()
        return save_api_config(config)
    except Exception as e:
        print(f"Error deleting encrypted provider API key for {provider}: {e}")
        return False
