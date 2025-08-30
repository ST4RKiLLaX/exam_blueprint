"""
Model configuration management for AI agents
"""
import json
import os
from datetime import datetime
from typing import Dict, Any

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "model_config.json")

DEFAULT_CONFIG = {
    "chat_model": "gpt-5",
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
    return config.get("chat_model", "gpt-5")

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
MODEL_PRICING = {
    "gpt-5": {
        "input": 0.10,
        "output": 0.10,
        "description": "Latest & Most Advanced - PhD-level expertise"
    },
    "gpt-4o": {
        "input": 0.05,
        "output": 0.05,
        "description": "High Performance - Optimized for speed"
    },
    "gpt-4-turbo": {
        "input": 0.03,
        "output": 0.03,
        "description": "Fast & Efficient - Good balance"
    },
    "gpt-4": {
        "input": 0.06,
        "output": 0.06,
        "description": "Reliable Standard - Original GPT-4"
    },
    "gpt-3.5-turbo": {
        "input": 0.002,
        "output": 0.002,
        "description": "Cost Effective - Good for simple tasks"
    }
}

def get_model_pricing(model: str) -> Dict[str, Any]:
    """Get pricing information for a specific model"""
    return MODEL_PRICING.get(model, MODEL_PRICING["gpt-5"])

def estimate_monthly_cost(model: str, emails_per_month: int, avg_tokens_per_email: int = 500) -> float:
    """Estimate monthly cost for a given usage pattern"""
    pricing = get_model_pricing(model)
    total_tokens = emails_per_month * avg_tokens_per_email
    cost_per_1k = pricing["input"]  # Simplified - using input pricing
    return (total_tokens / 1000) * cost_per_1k
