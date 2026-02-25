"""
API Key configuration management with secure storage
"""
import json
import os
from datetime import datetime
from cryptography.fernet import Fernet
from typing import Optional, Dict, Any, List, Tuple
import base64
import stat

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "api_config.json")
KEY_FILE = os.path.join(os.path.dirname(__file__), "api_encryption.key")
KEY_FILE_MODE = 0o600
DEFAULT_PROVIDER_KEY_NAME = "default"


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


def _normalize_provider_encrypted_map(
    config: Dict[str, Any],
) -> Tuple[Dict[str, Dict[str, str]], bool]:
    """
    Normalize provider_api_keys_encrypted to:
    {provider: {key_name: encrypted_value}}
    """
    raw_map = config.get("provider_api_keys_encrypted", {})
    changed = False

    if not isinstance(raw_map, dict):
        raw_map = {}
        changed = True

    normalized: Dict[str, Dict[str, str]] = {}
    for provider, value in raw_map.items():
        if not isinstance(provider, str) or not provider.strip():
            changed = True
            continue

        provider_id = provider.strip()
        if isinstance(value, str):
            if value:
                normalized[provider_id] = {DEFAULT_PROVIDER_KEY_NAME: value}
            changed = True
            continue

        if isinstance(value, dict):
            normalized_keys: Dict[str, str] = {}
            for key_name, encrypted_value in value.items():
                if (
                    isinstance(key_name, str)
                    and key_name.strip()
                    and isinstance(encrypted_value, str)
                    and encrypted_value
                ):
                    normalized_keys[key_name.strip()] = encrypted_value
                else:
                    changed = True
            if normalized_keys:
                normalized[provider_id] = normalized_keys
            if normalized_keys != value:
                changed = True
            continue

        changed = True

    if raw_map != normalized:
        changed = True
    return normalized, changed


def _migrate_legacy_openai_storage(config: Dict[str, Any]) -> bool:
    """
    Migrate legacy OpenAI storage into unified provider map.
    Returns True if config was changed.
    """
    provider_map, changed = _normalize_provider_encrypted_map(config)
    legacy_openai = config.get("openai_api_key_encrypted", "")

    if legacy_openai:
        openai_keys = provider_map.get("openai", {})
        if DEFAULT_PROVIDER_KEY_NAME not in openai_keys:
            openai_keys[DEFAULT_PROVIDER_KEY_NAME] = legacy_openai
            provider_map["openai"] = openai_keys
            changed = True

    if config.get("provider_api_keys_encrypted") != provider_map:
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
    """
    Get the current OpenAI API key from unified encrypted provider storage.

    Uses `default` when present. For backward compatibility with earlier UI key
    naming variations, falls back to a single available OpenAI key.
    """
    default_key = get_provider_api_key_encrypted("openai", DEFAULT_PROVIDER_KEY_NAME)
    if default_key:
        return default_key

    fallback_names = list_provider_api_key_names_encrypted("openai")
    if not fallback_names:
        return None

    # Prefer legacy-like variants first, then fall back to first configured key.
    preferred_candidates = ["default OpenAI", "openai", "default-openai"]
    for candidate in preferred_candidates:
        if candidate in fallback_names:
            key_value = get_provider_api_key_encrypted("openai", candidate)
            if key_value:
                return key_value

    if len(fallback_names) == 1:
        key_value = get_provider_api_key_encrypted("openai", fallback_names[0])
        if key_value:
            return key_value

    return None

def set_openai_api_key(api_key: str) -> bool:
    """Set and encrypt the OpenAI API key"""
    try:
        config = load_api_config()
        if _migrate_legacy_openai_storage(config):
            pass
        provider_map = config.get("provider_api_keys_encrypted", {})
        openai_map = provider_map.get("openai", {})
        if not isinstance(openai_map, dict):
            openai_map = {}
        openai_map[DEFAULT_PROVIDER_KEY_NAME] = _encrypt_api_key(api_key)
        provider_map["openai"] = openai_map
        
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
        _migrate_legacy_openai_storage(config)
        provider_map = config.get("provider_api_keys_encrypted", {})
        openai_map = provider_map.get("openai", {})
        if isinstance(openai_map, dict):
            openai_map.pop(DEFAULT_PROVIDER_KEY_NAME, None)
            if openai_map:
                provider_map["openai"] = openai_map
            elif "openai" in provider_map:
                del provider_map["openai"]
        elif "openai" in provider_map:
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

    if _migrate_legacy_openai_storage(config):
        save_api_config(config)

    provider_map = config.get("provider_api_keys_encrypted", {})
    if not isinstance(provider_map, dict):
        provider_map = {}

    total_keys = 0
    providers_with_keys = 0
    for provider_keys in provider_map.values():
        if not isinstance(provider_keys, dict):
            continue
        key_count = len(
            [
                encrypted_value
                for encrypted_value in provider_keys.values()
                if isinstance(encrypted_value, str) and encrypted_value
            ]
        )
        if key_count > 0:
            providers_with_keys += 1
            total_keys += key_count

    has_key = total_keys > 0
    if has_key:
        preview = f"{total_keys} key(s) across {providers_with_keys} provider(s)"
    else:
        preview = "Not Set"

    return {
        "has_key": has_key,
        "preview": preview,
        "last_updated": config.get("last_updated"),
        "last_tested": config.get("last_tested"),
        "test_status": config.get("test_status", "unknown"),
        "source": "Stored Encrypted (Provider Keys)"
    }


def _validate_provider_id(provider: str) -> str:
    if not isinstance(provider, str) or not provider.strip():
        raise ValueError("provider must be a non-empty string")
    return provider.strip()


def _validate_key_name(key_name: str) -> str:
    if not isinstance(key_name, str) or not key_name.strip():
        raise ValueError("key_name must be a non-empty string")
    return key_name.strip()


def list_provider_api_key_names_encrypted(provider: str) -> List[str]:
    """List key names configured for a provider."""
    provider_id = _validate_provider_id(provider)
    config = load_api_config()
    if _migrate_legacy_openai_storage(config):
        save_api_config(config)
    provider_map = config.get("provider_api_keys_encrypted", {})
    keys_map = provider_map.get(provider_id, {})
    if not isinstance(keys_map, dict):
        return []
    return sorted(keys_map.keys())


def get_provider_api_key_encrypted(provider: str, key_name: str = DEFAULT_PROVIDER_KEY_NAME) -> Optional[str]:
    """Get decrypted provider API key stored in encrypted config."""
    provider_id = _validate_provider_id(provider)
    selected_key_name = _validate_key_name(key_name)
    config = load_api_config()
    if _migrate_legacy_openai_storage(config):
        save_api_config(config)
    provider_map = config.get("provider_api_keys_encrypted", {})
    provider_keys = provider_map.get(provider_id, {})
    if not isinstance(provider_keys, dict):
        return None
    encrypted_key = provider_keys.get(selected_key_name)
    if encrypted_key:
        return _decrypt_api_key(encrypted_key)
    return None


def set_provider_api_key_encrypted(
    provider: str, api_key: str, key_name: str = DEFAULT_PROVIDER_KEY_NAME
) -> bool:
    """Set encrypted provider API key in shared encrypted config."""
    provider_id = _validate_provider_id(provider)
    selected_key_name = _validate_key_name(key_name)
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("api_key must be a non-empty string")
    try:
        config = load_api_config()
        _migrate_legacy_openai_storage(config)
        encrypted_keys = config.get("provider_api_keys_encrypted", {})
        provider_keys = encrypted_keys.get(provider_id, {})
        if not isinstance(provider_keys, dict):
            provider_keys = {}
        provider_keys[selected_key_name] = _encrypt_api_key(api_key.strip())
        encrypted_keys[provider_id] = provider_keys
        config["provider_api_keys_encrypted"] = encrypted_keys
        config["last_updated"] = datetime.now().isoformat()
        return save_api_config(config)
    except Exception as e:
        print(f"Error setting encrypted provider API key for {provider_id}: {e}")
        return False


def delete_provider_api_key_encrypted(
    provider: str, key_name: Optional[str] = DEFAULT_PROVIDER_KEY_NAME
) -> bool:
    """Delete encrypted provider API key from shared encrypted config."""
    provider_id = _validate_provider_id(provider)
    selected_key_name = (
        _validate_key_name(key_name) if key_name is not None else None
    )
    try:
        config = load_api_config()
        _migrate_legacy_openai_storage(config)
        encrypted_keys = config.get("provider_api_keys_encrypted", {})
        provider_keys = encrypted_keys.get(provider_id, {})
        if selected_key_name is None:
            encrypted_keys.pop(provider_id, None)
        elif isinstance(provider_keys, dict):
            provider_keys.pop(selected_key_name, None)
            if provider_keys:
                encrypted_keys[provider_id] = provider_keys
            else:
                encrypted_keys.pop(provider_id, None)
        else:
            encrypted_keys.pop(provider_id, None)
        config["provider_api_keys_encrypted"] = encrypted_keys
        config["last_updated"] = datetime.now().isoformat()
        return save_api_config(config)
    except Exception as e:
        print(f"Error deleting encrypted provider API key for {provider_id}: {e}")
        return False
