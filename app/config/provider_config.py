"""
Multi-provider configuration and API key management.
Supports OpenAI and Gemini with per-provider API keys.
"""

import json
import os
from typing import Optional, Dict
from app.config.api_config import (
    get_openai_api_key,
    set_openai_api_key,
    delete_openai_api_key,
    get_provider_api_key_encrypted,
    set_provider_api_key_encrypted,
    delete_provider_api_key_encrypted,
)

PROVIDER_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "providers.json")

SUPPORTED_PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "generation_models": [
            "gpt-5.2", "gpt-5.1", "gpt-5", "gpt-4.1", "gpt-4.1-mini",
            "gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"
        ],
        "embedding_models": ["text-embedding-3-large", "text-embedding-3-small"],
        "default_embedding_model": "text-embedding-3-large",
        "embedding_dimensions": 3072,
        "supports_responses_api": ["gpt-5.2", "gpt-5.1", "gpt-5"]
    },
    "gemini": {
        "name": "Google Gemini",
        "generation_models": [
            "gemini-3-pro-preview",
            "gemini-3-flash-preview",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite"
        ],
        "embedding_models": ["text-embedding-004"],
        "default_embedding_model": "text-embedding-004",
        "embedding_dimensions": 768,  # Gemini default
        "supports_thinking": ["gemini-3-pro-preview", "gemini-2.5-pro"]
    }
}

def load_provider_config() -> Dict:
    """Load provider configuration from JSON file"""
    default_config = {
        "providers": {
            "openai": {"enabled": False},
            "gemini": {"enabled": False}
        }
    }

    if not os.path.exists(PROVIDER_CONFIG_PATH):
        save_provider_config(default_config)
        config = default_config
    else:
        try:
            with open(PROVIDER_CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            config = default_config

    providers = config.setdefault("providers", {})
    changed = False

    for provider in SUPPORTED_PROVIDERS.keys():
        if provider not in providers:
            providers[provider] = {"enabled": False}
            changed = True
        if "enabled" not in providers[provider]:
            providers[provider]["enabled"] = False
            changed = True

    if _migrate_plaintext_provider_keys(config):
        changed = True

    if changed:
        save_provider_config(config)

    return config

def save_provider_config(config: Dict):
    """Save provider configuration to JSON file"""
    with open(PROVIDER_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def _migrate_plaintext_provider_keys(config: Dict) -> bool:
    """
    Migrate plaintext provider keys from providers.json to encrypted storage.
    Also removes legacy api_key fields to keep providers.json metadata-only.
    """
    providers = config.get("providers", {})
    changed = False

    env_key_map = {
        "openai": "OPENAI_API_KEY",
        "gemini": "GEMINI_API_KEY"
    }

    for provider in SUPPORTED_PROVIDERS.keys():
        provider_config = providers.setdefault(provider, {"enabled": False})

        legacy_plaintext = provider_config.get("api_key")
        if legacy_plaintext:
            if provider == "openai":
                set_openai_api_key(legacy_plaintext)
            else:
                set_provider_api_key_encrypted(provider, legacy_plaintext)
            provider_config["enabled"] = True
            changed = True

        # Optional bootstrapping from environment if encrypted store is empty
        has_encrypted = bool(
            get_openai_api_key() if provider == "openai"
            else get_provider_api_key_encrypted(provider)
        )
        if not has_encrypted:
            env_key = os.getenv(env_key_map[provider], "")
            if env_key:
                if provider == "openai":
                    set_openai_api_key(env_key)
                else:
                    set_provider_api_key_encrypted(provider, env_key)
                provider_config["enabled"] = True
                changed = True

        # Remove non-secret-incompatible legacy field
        if "api_key" in provider_config:
            del provider_config["api_key"]
            changed = True

    return changed

def get_provider_api_key(provider: str) -> Optional[str]:
    """Get API key for a specific provider"""
    if provider == "openai":
        return get_openai_api_key()
    return get_provider_api_key_encrypted(provider)

def set_provider_api_key(provider: str, api_key: str):
    """Set API key for a specific provider"""
    config = load_provider_config()
    if "providers" not in config:
        config["providers"] = {}
    if provider not in config["providers"]:
        config["providers"][provider] = {}

    if provider == "openai":
        if api_key:
            set_openai_api_key(api_key)
        else:
            delete_openai_api_key()
    else:
        if api_key:
            set_provider_api_key_encrypted(provider, api_key)
        else:
            delete_provider_api_key_encrypted(provider)

    config["providers"][provider]["enabled"] = bool(api_key)
    if "api_key" in config["providers"][provider]:
        del config["providers"][provider]["api_key"]
    save_provider_config(config)

def get_provider_models(provider: str, model_type: str = "generation") -> list:
    """Get available models for a provider"""
    if provider not in SUPPORTED_PROVIDERS:
        return []
    if model_type == "generation":
        return SUPPORTED_PROVIDERS[provider]["generation_models"]
    elif model_type == "embedding":
        return SUPPORTED_PROVIDERS[provider]["embedding_models"]
    return []

def is_provider_enabled(provider: str) -> bool:
    """Check if a provider is enabled (has valid API key)"""
    config = load_provider_config()
    provider_config = config.get("providers", {}).get(provider, {})
    return provider_config.get("enabled", False) and bool(get_provider_api_key(provider))

def get_enabled_providers() -> list:
    """Get list of enabled providers"""
    config = load_provider_config()
    enabled = []
    for provider_name in SUPPORTED_PROVIDERS.keys():
        if is_provider_enabled(provider_name):
            enabled.append(provider_name)
    return enabled
