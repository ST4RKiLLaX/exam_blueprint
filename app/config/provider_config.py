"""Dynamic provider registry and encrypted key management wrappers."""

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from app.config.api_config import (
    clear_active_provider_key_name,
    delete_provider_api_key_encrypted,
    DEFAULT_PROVIDER_KEY_NAME,
    get_active_provider_key_name,
    KeyResolutionError,
    ProviderUnknownError,
    resolve_provider_key,
    run_guarded_startup_migration,
    list_provider_api_key_names_encrypted,
    _mask_key_preview,
    set_provider_api_key_encrypted,
    set_active_provider_key_name,
)

PROVIDER_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "providers.json")
PROVIDER_MIGRATION_LOCK_FILE = os.path.join(
    os.path.dirname(__file__), ".provider_config_migration_startup.lock"
)
MODEL_SYNC_INTERVAL = timedelta(hours=24)
_AUTO_MODEL_SYNC_RUNNING = False
_STARTUP_PROVIDER_MIGRATION_DONE = False

REQUIRED_PROVIDER_FIELDS = (
    "name",
    "generation_models",
    "embedding_models",
    "default_embedding_model",
    "embedding_dimensions",
)

DEFAULT_PROVIDER_REGISTRY = {
    "openai": {
        "name": "OpenAI",
        "generation_models": [
            "gpt-5.2",
            "gpt-5.1",
            "gpt-5",
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-3.5-turbo",
        ],
        "embedding_models": ["text-embedding-3-large", "text-embedding-3-small"],
        "default_embedding_model": "text-embedding-3-large",
        "embedding_dimensions": 3072,
        "supports_responses_api": ["gpt-5.2", "gpt-5.1", "gpt-5"],
        "supports_thinking": [],
    },
    "gemini": {
        "name": "Google Gemini",
        "generation_models": [
            "gemini-3-pro-preview",
            "gemini-3-flash-preview",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
        ],
        "embedding_models": ["gemini-embedding-001", "gemini-embedding-2-preview"],
        "default_embedding_model": "gemini-embedding-001",
        "embedding_dimensions": 3072,
        "supports_responses_api": [],
        "supports_thinking": ["gemini-3-pro-preview", "gemini-2.5-pro"],
    },
}


def _default_provider_config() -> Dict:
    providers = {}
    for provider_id, metadata in DEFAULT_PROVIDER_REGISTRY.items():
        providers[provider_id] = {**metadata, "enabled": False}
    return {"providers": providers}

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

def _parse_utc_timestamp(value: str) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None

def _is_sync_due(provider_data: Dict) -> bool:
    last_synced = _parse_utc_timestamp(provider_data.get("models_last_synced_at", ""))
    if not last_synced:
        return True
    return (_utc_now() - last_synced) >= MODEL_SYNC_INTERVAL

def _normalize_generation_model_names(models: List[str], provider_id: str) -> List[str]:
    cleaned = []
    for model_name in models:
        if not isinstance(model_name, str):
            continue
        candidate = model_name.strip()
        if not candidate:
            continue
        lowered = candidate.lower()
        if "embedding" in lowered:
            continue
        if provider_id == "openai" and not lowered.startswith("gpt-"):
            continue
        if provider_id == "gemini" and "gemini" not in lowered:
            continue
        cleaned.append(candidate)
    return sorted(set(cleaned))

def _fetch_openai_generation_models(api_key: str) -> List[str]:
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    response = client.models.list()
    model_names = []
    for model in getattr(response, "data", []):
        model_id = getattr(model, "id", None)
        if isinstance(model_id, str):
            model_names.append(model_id)
    return _normalize_generation_model_names(model_names, "openai")

def _fetch_gemini_generation_models(api_key: str) -> List[str]:
    from google import genai
    client = genai.Client(api_key=api_key)
    model_names = []
    for model in client.models.list():
        raw_name = getattr(model, "name", "")
        if isinstance(raw_name, str):
            model_names.append(raw_name.replace("models/", ""))
    return _normalize_generation_model_names(model_names, "gemini")

def _sync_provider_models_internal(
    config: Dict, provider_ids: Optional[List[str]] = None, force: bool = False
) -> Dict[str, object]:
    providers = config.get("providers", {})
    target_ids = provider_ids or list(providers.keys())

    summary: Dict[str, object] = {
        "success_count": 0,
        "failure_count": 0,
        "skipped_count": 0,
        "results": {},
    }

    for provider_id in target_ids:
        provider_data = providers.get(provider_id)
        if not isinstance(provider_data, dict):
            continue

        results = summary["results"]  # type: ignore[assignment]
        if not force and not provider_data.get("enabled", False):
            results[provider_id] = {"status": "skipped", "reason": "provider_disabled"}
            summary["skipped_count"] = summary["skipped_count"] + 1
            continue

        if not force and not _is_sync_due(provider_data):
            results[provider_id] = {"status": "skipped", "reason": "not_due"}
            summary["skipped_count"] = summary["skipped_count"] + 1
            continue

        raw_requested = provider_data.get("models_sync_key_name")
        requested_key_name = (
            raw_requested.strip()
            if isinstance(raw_requested, str) and raw_requested.strip()
            else None
        )
        try:
            resolved_key = resolve_provider_key(
                provider_id,
                key_name=requested_key_name,
                purpose="model_sync",
            )
            key_name = resolved_key["key_name_used"]
            api_key = resolved_key["key_value"]
        except KeyResolutionError as error:
            provider_data["models_last_sync_status"] = "warning"
            provider_data["models_last_sync_error"] = str(error)
            results[provider_id] = {"status": "warning", "reason": "no_key"}
            summary["failure_count"] = summary["failure_count"] + 1
            continue

        try:
            if provider_id == "openai":
                fetched_models = _fetch_openai_generation_models(api_key)
            elif provider_id == "gemini":
                fetched_models = _fetch_gemini_generation_models(api_key)
            else:
                results[provider_id] = {"status": "skipped", "reason": "provider_not_supported"}
                summary["skipped_count"] = summary["skipped_count"] + 1
                continue

            if fetched_models:
                provider_data["generation_models"] = fetched_models
                provider_data["models_last_sync_status"] = "success"
                provider_data["models_last_sync_error"] = ""
                provider_data["models_last_synced_at"] = _utc_now().isoformat()
                results[provider_id] = {"status": "success", "models_count": len(fetched_models)}
                summary["success_count"] = summary["success_count"] + 1
            else:
                provider_data["models_last_sync_status"] = "warning"
                provider_data["models_last_sync_error"] = "Provider returned no generation models"
                provider_data["models_last_synced_at"] = _utc_now().isoformat()
                results[provider_id] = {"status": "warning", "reason": "no_models"}
                summary["failure_count"] = summary["failure_count"] + 1
        except Exception as error:
            provider_data["models_last_sync_status"] = "warning"
            provider_data["models_last_sync_error"] = str(error)
            provider_data["models_last_synced_at"] = _utc_now().isoformat()
            results[provider_id] = {"status": "warning", "reason": str(error)}
            summary["failure_count"] = summary["failure_count"] + 1

    return summary

def sync_provider_models(
    provider_id: Optional[str] = None, force: bool = True
) -> Dict[str, object]:
    """Manual sync entrypoint for one provider or all providers."""
    config = load_provider_config(run_auto_sync=False)
    targets = [provider_id] if provider_id else None
    summary = _sync_provider_models_internal(config, targets, force=force)
    save_provider_config(config)
    return summary

def _run_due_auto_sync(config: Dict) -> Tuple[bool, Dict[str, object]]:
    global _AUTO_MODEL_SYNC_RUNNING
    if _AUTO_MODEL_SYNC_RUNNING:
        return False, {"status": "skipped", "reason": "sync_in_progress"}

    providers = config.get("providers", {})
    due_targets = []
    for provider_id, provider_data in providers.items():
        if not isinstance(provider_data, dict):
            continue
        if provider_data.get("enabled", False) and _is_sync_due(provider_data):
            due_targets.append(provider_id)

    if not due_targets:
        return False, {"status": "skipped", "reason": "no_due_providers"}

    _AUTO_MODEL_SYNC_RUNNING = True
    try:
        summary = _sync_provider_models_internal(config, due_targets, force=False)
        return True, summary
    finally:
        _AUTO_MODEL_SYNC_RUNNING = False


def _validate_provider_structure(provider_id: str, provider_data: Dict) -> None:
    if not isinstance(provider_data, dict):
        raise ValueError(f"Provider '{provider_id}' must be an object")

    for field in REQUIRED_PROVIDER_FIELDS:
        if field not in provider_data:
            raise ValueError(f"Provider '{provider_id}' missing required field '{field}'")

    if not isinstance(provider_data["name"], str) or not provider_data["name"].strip():
        raise ValueError(f"Provider '{provider_id}' must have a non-empty 'name'")

    for list_field in ("generation_models", "embedding_models"):
        value = provider_data.get(list_field)
        if not isinstance(value, list) or not value or not all(
            isinstance(item, str) and item.strip() for item in value
        ):
            raise ValueError(
                f"Provider '{provider_id}' field '{list_field}' must be a non-empty string list"
            )

    if provider_data["default_embedding_model"] not in provider_data["embedding_models"]:
        raise ValueError(
            f"Provider '{provider_id}' default_embedding_model must be in embedding_models"
        )

    if not isinstance(provider_data["embedding_dimensions"], int) or provider_data[
        "embedding_dimensions"
    ] <= 0:
        raise ValueError(
            f"Provider '{provider_id}' field 'embedding_dimensions' must be a positive integer"
        )

    supports_responses = provider_data.get("supports_responses_api", [])
    supports_thinking = provider_data.get("supports_thinking", [])
    if not isinstance(supports_responses, list) or not all(
        isinstance(item, str) for item in supports_responses
    ):
        raise ValueError(
            f"Provider '{provider_id}' field 'supports_responses_api' must be a string list"
        )
    if not isinstance(supports_thinking, list) or not all(
        isinstance(item, str) for item in supports_thinking
    ):
        raise ValueError(
            f"Provider '{provider_id}' field 'supports_thinking' must be a string list"
        )


def save_provider_config(config: Dict) -> None:
    """Save provider configuration to JSON file."""
    with open(PROVIDER_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def _migrate_plaintext_provider_keys(config: Dict) -> bool:
    """
    Migrate plaintext provider keys from providers.json to encrypted storage.
    Also removes legacy api_key fields to keep providers.json metadata-only.
    """
    providers = config.get("providers", {})
    changed = False

    for provider_id, provider_config in providers.items():
        if not isinstance(provider_config, dict):
            continue

        legacy_plaintext = provider_config.get("api_key")
        if isinstance(legacy_plaintext, str) and legacy_plaintext.strip():
            set_provider_api_key_encrypted(
                provider_id, legacy_plaintext.strip(), DEFAULT_PROVIDER_KEY_NAME
            )
            provider_config["enabled"] = True
            changed = True

        if "api_key" in provider_config:
            del provider_config["api_key"]
            changed = True

    return changed


def run_startup_provider_config_migration() -> bool:
    """
    Guarded, idempotent startup migration for providers.json legacy plaintext keys.
    No read path should mutate files.
    """
    global _STARTUP_PROVIDER_MIGRATION_DONE
    if _STARTUP_PROVIDER_MIGRATION_DONE:
        return False

    def _migrate_once() -> bool:
        if not os.path.exists(PROVIDER_CONFIG_PATH):
            return False
        try:
            with open(PROVIDER_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            return False
        changed = _migrate_plaintext_provider_keys(cfg)
        if changed:
            save_provider_config(cfg)
        return changed

    ran = run_guarded_startup_migration(PROVIDER_MIGRATION_LOCK_FILE, _migrate_once)
    _STARTUP_PROVIDER_MIGRATION_DONE = True
    return ran


def load_provider_config(run_auto_sync: bool = True) -> Dict:
    """Load and validate provider configuration from JSON file."""
    default_config = _default_provider_config()

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

    # Ensure default providers always exist and backfill legacy minimal entries.
    for provider_id, default_metadata in DEFAULT_PROVIDER_REGISTRY.items():
        provider_config = providers.get(provider_id)
        if not isinstance(provider_config, dict):
            providers[provider_id] = {**default_metadata, "enabled": False}
            changed = True
            continue

        if "enabled" not in provider_config:
            provider_config["enabled"] = False
            changed = True
        elif not isinstance(provider_config.get("enabled"), bool):
            provider_config["enabled"] = bool(provider_config.get("enabled"))
            changed = True

        for field, value in default_metadata.items():
            if field not in provider_config:
                provider_config[field] = value
                changed = True

    # Strict schema validation for all configured providers.
    for provider_id, provider_data in providers.items():
        _validate_provider_structure(provider_id, provider_data)

    if run_auto_sync:
        try:
            sync_changed, _ = _run_due_auto_sync(config)
            if sync_changed:
                changed = True
        except Exception as sync_error:
            # Non-blocking by design: keep cached model list on sync failure.
            print(f"[WARN] Provider model auto-sync skipped: {sync_error}")

    if changed:
        save_provider_config(config)

    return config


def get_provider_registry() -> Dict[str, Dict]:
    """Get provider metadata registry keyed by provider id."""
    providers = load_provider_config().get("providers", {})
    registry: Dict[str, Dict] = {}
    for provider_id, provider_data in providers.items():
        metadata = dict(provider_data)
        metadata.pop("enabled", None)
        metadata.pop("api_key", None)
        registry[provider_id] = metadata
    return registry


def get_provider_metadata(provider: str) -> Dict:
    """Get metadata for a provider id."""
    return get_provider_registry().get(provider, {})


def get_provider_api_key(provider: str, key_name: Optional[str] = None) -> Optional[str]:
    """Resolver-backed wrapper for provider key retrieval."""
    providers = load_provider_config(run_auto_sync=False).get("providers", {})
    if provider not in providers:
        raise ProviderUnknownError(f"Unknown provider: {provider}")
    resolved = resolve_provider_key(
        provider,
        key_name=key_name,
        purpose="provider_api_key",
    )
    return resolved["key_value"]


def list_provider_key_names(provider: str) -> List[str]:
    """List named keys for a provider."""
    if provider not in load_provider_config().get("providers", {}):
        raise ValueError(f"Unknown provider: {provider}")
    return list_provider_api_key_names_encrypted(provider)

def get_provider_key_rows(provider: str) -> List[Dict[str, object]]:
    """List provider keys with description and masked preview."""
    config = load_provider_config()
    providers = config.get("providers", {})
    if provider not in providers:
        raise ValueError(f"Unknown provider: {provider}")

    provider_cfg = providers[provider]
    key_descriptions = provider_cfg.get("key_descriptions", {})
    if not isinstance(key_descriptions, dict):
        key_descriptions = {}

    active_key_name = get_active_provider_key_name(provider)
    rows: List[Dict[str, object]] = []
    for key_name in list_provider_key_names(provider):
        row_error = ""
        try:
            key_value = get_provider_api_key(provider, key_name) or ""
        except KeyResolutionError as exc:
            key_value = ""
            row_error = str(exc)
        rows.append(
            {
                "key_name": key_name,
                "description": str(key_descriptions.get(key_name, "")),
                "key_preview": _mask_key_preview(key_value),
                "is_default": key_name == active_key_name,
                "error": row_error,
            }
        )
    return rows

def set_provider_key_description(provider: str, key_name: str, description: str) -> None:
    """Set/update non-secret description for a provider key."""
    config = load_provider_config()
    providers = config.setdefault("providers", {})
    if provider not in providers:
        raise ValueError(f"Unknown provider: {provider}")

    provider_cfg = providers[provider]
    key_desc = provider_cfg.get("key_descriptions", {})
    if not isinstance(key_desc, dict):
        key_desc = {}
    key_desc[key_name] = (description or "").strip()
    provider_cfg["key_descriptions"] = key_desc
    save_provider_config(config)

def remove_provider_key_description(provider: str, key_name: str) -> None:
    """Remove key description when key is deleted."""
    config = load_provider_config()
    providers = config.setdefault("providers", {})
    if provider not in providers:
        raise ValueError(f"Unknown provider: {provider}")
    provider_cfg = providers[provider]
    key_desc = provider_cfg.get("key_descriptions", {})
    if isinstance(key_desc, dict) and key_name in key_desc:
        del key_desc[key_name]
        provider_cfg["key_descriptions"] = key_desc
        save_provider_config(config)


def set_provider_default_key(provider: str, key_name: str) -> None:
    """Mark one existing key as the active/default key for provider."""
    providers = load_provider_config(run_auto_sync=False).get("providers", {})
    if provider not in providers:
        raise ValueError(f"Unknown provider: {provider}")
    names = list_provider_key_names(provider)
    if key_name not in names:
        raise ValueError(f"Key '{key_name}' not found for provider '{provider}'")
    set_active_provider_key_name(provider, key_name)


def set_provider_api_key(
    provider: str,
    api_key: str,
    key_name: str = "default",
    make_default: bool = False,
) -> None:
    """Set encrypted API key for a provider/key-name pair."""
    config = load_provider_config()
    providers = config.setdefault("providers", {})
    if provider not in providers:
        raise ValueError(f"Unknown provider: {provider}")
    provider_settings = providers[provider]

    selected_key_name = key_name or DEFAULT_PROVIDER_KEY_NAME
    if api_key:
        set_provider_api_key_encrypted(provider, api_key, selected_key_name)
        if make_default:
            set_active_provider_key_name(provider, selected_key_name)
    else:
        delete_provider_api_key_encrypted(provider, selected_key_name)
        if get_active_provider_key_name(provider) == selected_key_name:
            clear_active_provider_key_name(provider)

    provider_settings["enabled"] = bool(list_provider_key_names(provider))
    provider_settings.pop("api_key", None)
    save_provider_config(config)


def delete_provider_api_key(provider: str, key_name: Optional[str] = None) -> None:
    """Delete one named key or all keys for a provider."""
    providers = load_provider_config().get("providers", {})
    if provider not in providers:
        raise ValueError(f"Unknown provider: {provider}")
    delete_provider_api_key_encrypted(provider, key_name)
    if key_name and get_active_provider_key_name(provider) == key_name:
        clear_active_provider_key_name(provider)
    if key_name:
        remove_provider_key_description(provider, key_name)

    config = load_provider_config()
    provider_settings = config.setdefault("providers", {}).setdefault(provider, {"enabled": False})
    provider_settings["enabled"] = bool(list_provider_key_names(provider))
    save_provider_config(config)


def get_provider_models(provider: str, model_type: str = "generation") -> List[str]:
    """Get available generation or embedding models for a provider."""
    metadata = get_provider_metadata(provider)
    if not metadata:
        return []
    if model_type == "generation":
        return metadata.get("generation_models", [])
    if model_type == "embedding":
        return metadata.get("embedding_models", [])
    return []


def is_provider_enabled(provider: str) -> bool:
    """Check if a provider is enabled and has at least one configured key."""
    config = load_provider_config()
    provider_config = config.get("providers", {}).get(provider, {})
    return provider_config.get("enabled", False) and bool(list_provider_key_names(provider))


def get_enabled_providers() -> List[str]:
    """Get list of enabled providers."""
    config = load_provider_config()
    enabled: List[str] = []
    for provider_id in config.get("providers", {}):
        if is_provider_enabled(provider_id):
            enabled.append(provider_id)
    return enabled


def get_effective_key_diagnostics() -> List[Dict[str, str]]:
    """
    Minimal admin diagnostics showing effective logical key selection per provider.
    Never returns secret values.
    """
    diagnostics: List[Dict[str, str]] = []
    config = load_provider_config(run_auto_sync=False)
    for provider_id in config.get("providers", {}):
        row: Dict[str, str] = {
            "provider_id": provider_id,
            "configured_default_key_name": get_active_provider_key_name(provider_id) or "",
        }
        try:
            resolved = resolve_provider_key(provider_id, key_name=None, purpose="diagnostics")
            row["key_name_used"] = resolved.get("key_name_used", "")
            row["resolution_code"] = resolved.get("resolution_code", "")
        except KeyResolutionError as exc:
            row["key_name_used"] = ""
            row["resolution_code"] = "unresolved"
            row["error"] = str(exc)
        diagnostics.append(row)
    return diagnostics


# Backward-compatible alias used by other modules.
SUPPORTED_PROVIDERS = get_provider_registry()
