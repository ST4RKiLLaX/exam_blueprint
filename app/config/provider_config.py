"""
Multi-provider configuration and API key management.
Supports OpenAI and Gemini with per-provider API keys.
"""

import json
import os
from typing import Optional, Dict

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
    if not os.path.exists(PROVIDER_CONFIG_PATH):
        default_config = {
            "providers": {
                "openai": {"api_key": os.getenv("OPENAI_API_KEY", ""), "enabled": True},
                "gemini": {"api_key": os.getenv("GEMINI_API_KEY", ""), "enabled": False}
            }
        }
        save_provider_config(default_config)
        return default_config
    
    with open(PROVIDER_CONFIG_PATH, "r") as f:
        return json.load(f)

def save_provider_config(config: Dict):
    """Save provider configuration to JSON file"""
    with open(PROVIDER_CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)

def get_provider_api_key(provider: str) -> Optional[str]:
    """Get API key for a specific provider"""
    config = load_provider_config()
    return config.get("providers", {}).get(provider, {}).get("api_key")

def set_provider_api_key(provider: str, api_key: str):
    """Set API key for a specific provider"""
    config = load_provider_config()
    if "providers" not in config:
        config["providers"] = {}
    if provider not in config["providers"]:
        config["providers"][provider] = {}
    config["providers"][provider]["api_key"] = api_key
    config["providers"][provider]["enabled"] = bool(api_key)
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
    return provider_config.get("enabled", False) and bool(provider_config.get("api_key"))

def get_enabled_providers() -> list:
    """Get list of enabled providers"""
    config = load_provider_config()
    enabled = []
    for provider_name in SUPPORTED_PROVIDERS.keys():
        if is_provider_enabled(provider_name):
            enabled.append(provider_name)
    return enabled
