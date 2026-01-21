"""
Model configuration management for AI agents
"""
import json
import os
from datetime import datetime
from typing import Dict, Any

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "model_config.json")

DEFAULT_CONFIG = {
    "chat_model": "gpt-4.1-mini",
    "temperature": 0.5,
    "max_tokens": 1000,
    "updated_at": datetime.now().isoformat()
}

def load_model_config() -> Dict[str, Any]:
    """Load model configuration from file"""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading model config: {e}")
    
    return DEFAULT_CONFIG.copy()

def save_model_config(config: Dict[str, Any]) -> bool:
    """Save model configuration to file"""
    try:
        config["updated_at"] = datetime.now().isoformat()
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving model config: {e}")
        return False

def get_current_model() -> str:
    """Get the currently configured chat model"""
    config = load_model_config()
    return config.get("chat_model", "gpt-4.1-mini")

def get_current_temperature() -> float:
    """Get the currently configured temperature"""
    config = load_model_config()
    return config.get("temperature", 0.5)

def update_model_settings(chat_model: str = None, temperature: float = None) -> bool:
    """Update model settings"""
    config = load_model_config()
    
    if chat_model:
        config["chat_model"] = chat_model
    if temperature is not None:
        config["temperature"] = temperature
    
    return save_model_config(config)

# Model pricing information (approximate, in USD per 1K tokens)
# Note: Verify current pricing at https://platform.openai.com/docs/pricing
MODEL_PRICING = {
    "gpt-5.2": {
        "input": 0.005,  # Estimated - verify at platform.openai.com
        "output": 0.015,
        "description": "Latest Generation - Best for coding and agentic tasks"
    },
    "gpt-5.1": {
        "input": 0.004,  # Estimated - verify at platform.openai.com
        "output": 0.012,
        "description": "Advanced - Improved personality and multimodal reasoning"
    },
    "gpt-5": {
        "input": 0.003,  # Estimated - verify at platform.openai.com
        "output": 0.010,
        "description": "Baseline GPT-5 - Balanced capability and cost"
    },
    "gpt-4.1": {
        "input": 0.0035,  # Estimated - verify at platform.openai.com
        "output": 0.012,
        "description": "Large Context - Up to 1M tokens, excellent for technical tasks"
    },
    "gpt-4.1-mini": {
        "input": 0.0008,  # Estimated - verify at platform.openai.com
        "output": 0.003,
        "description": "Efficient - Faster and more affordable GPT-4.1"
    },
    "gpt-4o": {
        "input": 0.0025,
        "output": 0.010,
        "description": "Multimodal - Text, audio, image (Deprecating Feb 16, 2026)"
    },
    "gpt-4o-mini": {
        "input": 0.00015,
        "output": 0.0006,
        "description": "Budget Multimodal - Lower cost alternative"
    },
    "gpt-3.5-turbo": {
        "input": 0.0005,
        "output": 0.0015,
        "description": "Legacy - Most cost effective for simple tasks"
    }
}

def get_model_pricing(model: str) -> Dict[str, Any]:
    """Get pricing information for a specific model"""
    return MODEL_PRICING.get(model, MODEL_PRICING.get("gpt-4.1-mini", {}))

def estimate_monthly_cost(model: str, emails_per_month: int, avg_tokens_per_email: int = 500) -> float:
    """Estimate monthly cost for a given usage pattern"""
    pricing = get_model_pricing(model)
    total_tokens = emails_per_month * avg_tokens_per_email
    cost_per_1k = pricing["input"]  # Simplified - using input pricing
    return (total_tokens / 1000) * cost_per_1k

def should_use_responses_api(model: str) -> bool:
    """
    Determine if a model should use the Responses API instead of Chat Completions API.
    GPT-5.x models require the Responses API for proper parameter support.
    """
    model_lower = model.lower()
    return model_lower in ["gpt-5.2", "gpt-5.1", "gpt-5"]

def get_model_parameters(model: str) -> Dict[str, Any]:
    """
    Get parameter configuration for a specific model.
    Returns information about which parameters are supported and how to use them.
    """
    model_lower = model.lower()
    
    # GPT-5.2 - Latest with reasoning and verbosity
    if model_lower == "gpt-5.2":
        return {
            "family": "gpt-5.2",
            "uses_responses_api": True,
            "uses_completion_tokens": True,
            "token_param": "max_completion_tokens",
            "supports": ["temperature", "top_p", "max_completion_tokens", "max_output_tokens", 
                        "stop", "reasoning_effort", "verbosity"],
            "supports_penalties": False,
            "supports_reasoning": True,
            "requires_nested_params": True  # reasoning: {effort}, text: {verbosity}
        }
    
    # GPT-5.1 and GPT-5 - Older GPT-5 series
    elif model_lower in ["gpt-5.1", "gpt-5"]:
        return {
            "family": "gpt-5",
            "uses_responses_api": True,
            "uses_completion_tokens": True,
            "token_param": "max_completion_tokens",
            "supports": ["temperature", "top_p", "max_completion_tokens", "stop", 
                        "presence_penalty", "frequency_penalty", "reasoning_effort"],
            "supports_penalties": True,
            "supports_reasoning": True,
            "requires_nested_params": True  # reasoning: {effort}
        }
    
    # GPT-4.1, GPT-4o, GPT-4o-mini - GPT-4 series
    elif model_lower in ["gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini"]:
        return {
            "family": "gpt-4",
            "uses_responses_api": False,
            "uses_completion_tokens": False,
            "token_param": "max_tokens",
            "supports": ["temperature", "top_p", "max_tokens", "presence_penalty", 
                        "frequency_penalty", "stop"],
            "supports_penalties": True,
            "supports_reasoning": False,
            "requires_nested_params": False
        }
    
    # GPT-3.5-turbo - Legacy
    elif model_lower == "gpt-3.5-turbo":
        return {
            "family": "gpt-3.5",
            "uses_responses_api": False,
            "uses_completion_tokens": False,
            "token_param": "max_tokens",
            "supports": ["temperature", "top_p", "max_tokens", "presence_penalty", 
                        "frequency_penalty", "stop"],
            "supports_penalties": True,
            "supports_reasoning": False,
            "requires_nested_params": False
        }
    
    # Default fallback (assume GPT-4 style)
    else:
        return {
            "family": "unknown",
            "uses_responses_api": False,
            "uses_completion_tokens": False,
            "token_param": "max_tokens",
            "supports": ["temperature", "top_p", "max_tokens", "presence_penalty", 
                        "frequency_penalty", "stop"],
            "supports_penalties": True,
            "supports_reasoning": False,
            "requires_nested_params": False
        }
