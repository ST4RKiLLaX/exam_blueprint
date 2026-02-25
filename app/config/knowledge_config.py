# Knowledge Base Configuration
import json
import os
import hashlib
import zipfile
import tempfile
import shutil
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

KNOWLEDGE_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "knowledge_bases.json")
PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Default knowledge bases structure - no hardcoded defaults
DEFAULT_KNOWLEDGE_BASES = {
    "knowledge_bases": []
}

MAX_IMPORT_ZIP_BYTES = 100 * 1024 * 1024
MAX_IMPORT_MEMBER_BYTES = 500 * 1024 * 1024
CHUNKS_JSON_GZ = "chunks.json.gz"
LEGACY_CHUNKS_GZ = "chunks.pkl.gz"


def _safe_member_path(root_dir: str, member_name: str) -> Optional[str]:
    normalized = os.path.normpath(member_name)
    if normalized.startswith("..") or os.path.isabs(normalized):
        return None
    return os.path.abspath(os.path.join(root_dir, normalized))


def _validate_zip_integrity(zip_file) -> tuple[bool, str]:
    """Validate zip structure and reject unsafe entries."""
    try:
        zip_file.seek(0, os.SEEK_END)
        size = zip_file.tell()
        zip_file.seek(0)
    except Exception:
        return False, "Unable to read uploaded ZIP file"

    if size <= 0:
        return False, "Uploaded ZIP is empty"
    if size > MAX_IMPORT_ZIP_BYTES:
        return False, "ZIP package exceeds size limit"

    try:
        with zipfile.ZipFile(zip_file, "r") as zf:
            for info in zf.infolist():
                if _safe_member_path("/tmp", info.filename) is None:
                    return False, f"Unsafe ZIP path: {info.filename}"
                if info.file_size > MAX_IMPORT_MEMBER_BYTES:
                    return False, f"ZIP member exceeds size limit: {info.filename}"
            bad_file = zf.testzip()
            if bad_file:
                return False, f"Corrupted ZIP member: {bad_file}"
    except zipfile.BadZipFile:
        return False, "Invalid ZIP format"
    except Exception:
        return False, "Unable to validate ZIP contents"
    finally:
        try:
            zip_file.seek(0)
        except Exception:
            pass

    return True, ""


def _extract_zip_safely(zip_file, target_dir: str) -> tuple[bool, str]:
    """Extract ZIP entries with path traversal protections."""
    try:
        with zipfile.ZipFile(zip_file, "r") as zf:
            for info in zf.infolist():
                dest_path = _safe_member_path(target_dir, info.filename)
                if dest_path is None:
                    return False, f"Unsafe ZIP path: {info.filename}"
                if info.is_dir():
                    os.makedirs(dest_path, exist_ok=True)
                    continue
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                with zf.open(info, "r") as src, open(dest_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
    except Exception:
        return False, "Failed to extract ZIP package"
    finally:
        try:
            zip_file.seek(0)
        except Exception:
            pass

    return True, ""


def _sha256_for_file(path: str) -> Optional[str]:
    if not os.path.exists(path):
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _to_posix_relative(path_value: str) -> str:
    return path_value.replace("\\", "/")


def _kb_relative_source_path_from_absolute(abs_path: str) -> Optional[str]:
    """
    Convert an absolute local KB file path to project-relative form.
    """
    try:
        normalized_abs = os.path.normpath(abs_path)
        rel_to_project = os.path.relpath(normalized_abs, PROJECT_ROOT)
        rel_posix = _to_posix_relative(rel_to_project)
        if rel_posix.startswith("app/knowledge_bases/"):
            return rel_posix
    except Exception:
        return None
    return None


def _normalize_kb_source_for_storage(source_path: Optional[str]) -> Optional[str]:
    """
    Normalize KB source storage to project-relative paths when possible.
    """
    if not source_path or not isinstance(source_path, str):
        return source_path

    normalized_source = source_path.strip()
    if not normalized_source:
        return normalized_source

    resolved_source = _resolve_kb_source_path(normalized_source)
    if not resolved_source:
        return _to_posix_relative(normalized_source)

    relative_source = _kb_relative_source_path_from_absolute(resolved_source)
    if relative_source:
        return relative_source

    return _to_posix_relative(normalized_source)


def _resolve_kb_source_path(source_path: Optional[str]) -> Optional[str]:
    """
    Resolve a KB source path across environments.

    Supports legacy absolute paths (including Windows paths) by falling back
    to local knowledge base storage using filename matching.
    """
    if not source_path or not isinstance(source_path, str):
        return None

    normalized_source = source_path.strip()
    if os.path.exists(normalized_source):
        return os.path.normpath(normalized_source)

    # Resolve project-relative paths like app/knowledge_bases/<filename>.
    project_relative_candidate = os.path.normpath(
        os.path.join(PROJECT_ROOT, normalized_source)
    )
    if os.path.exists(project_relative_candidate):
        return project_relative_candidate

    source_filename = os.path.basename(normalized_source.replace("\\", "/"))
    if not source_filename:
        return None

    app_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
    candidate_paths = [
        os.path.join(app_dir, "knowledge_bases", source_filename),
        os.path.join(os.getcwd(), "app", "knowledge_bases", source_filename),
        os.path.join(os.getcwd(), "knowledge_bases", source_filename),
    ]

    for candidate in candidate_paths:
        if os.path.exists(candidate):
            return candidate

    return None

def load_knowledge_config():
    """Load knowledge bases configuration from JSON file"""
    if not os.path.exists(KNOWLEDGE_CONFIG_PATH):
        save_knowledge_config(DEFAULT_KNOWLEDGE_BASES)
        return DEFAULT_KNOWLEDGE_BASES
    
    try:
        with open(KNOWLEDGE_CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
        changed = False
        for kb in config.get("knowledge_bases", []):
            if not isinstance(kb, dict):
                continue
            kb_type = str(kb.get("type", "")).strip().lower()
            if kb_type in {"url", "embedded"}:
                continue
            normalized_source = _normalize_kb_source_for_storage(kb.get("source"))
            if normalized_source and normalized_source != kb.get("source"):
                kb["source"] = normalized_source
                changed = True
        if changed:
            save_knowledge_config(config)
        return config
    except (json.JSONDecodeError, FileNotFoundError):
        return DEFAULT_KNOWLEDGE_BASES

def save_knowledge_config(config):
    """Save knowledge bases configuration to JSON file"""
    with open(KNOWLEDGE_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def update_embedding_status(kb_id, status):
    """Update the embedding status of a knowledge base"""
    config = load_knowledge_config()
    for kb in config["knowledge_bases"]:
        if kb["id"] == kb_id:
            kb["embedding_status"] = status
            save_knowledge_config(config)
            return True
    return False

def add_knowledge_base(title, description, kb_type, source, chunks_path=None, access_type="shared", category="general", refresh_schedule="manual", exam_profile_ids=None, profile_type=None, profile_domain=None, is_priority_kb=False, embedding_provider="openai", embedding_model=None, cissp_type=None, cissp_domain=None, exam_profile_id=None):
    """Add a new knowledge base to the configuration"""
    config = load_knowledge_config()
    
    # Generate unique ID
    kb_id = f"kb_{len(config['knowledge_bases'])}_{int(datetime.now().timestamp())}"
    
    # Handle backward compatibility: cissp_* params map to profile_* fields
    if profile_type is None and cissp_type is not None:
        profile_type = cissp_type
    if profile_domain is None and cissp_domain is not None:
        profile_domain = cissp_domain
    
    # Handle backward compatibility: exam_profile_id → exam_profile_ids
    if exam_profile_ids is None and exam_profile_id is not None:
        exam_profile_ids = [exam_profile_id] if exam_profile_id else []
    elif exam_profile_ids is None:
        exam_profile_ids = []

    source_value = source
    if kb_type in {"document", "file"}:
        source_value = _normalize_kb_source_for_storage(source)
    
    new_kb = {
        "id": kb_id,
        "title": title,
        "description": description,
        "type": kb_type,
        "source": source_value,
        "chunks_path": chunks_path,
        "created_at": datetime.now().isoformat(),
        "exam_profile_ids": exam_profile_ids,  # List of profile IDs
        "status": "active",
        "access_type": access_type,  # "shared" or "exclusive"
        "category": category,  # "general", "cna", "pharmacy", "admin", etc.
        "refresh_schedule": refresh_schedule,  # "manual", "hourly", "daily", "weekly", "on_use"
        "last_refreshed": datetime.now().isoformat() if kb_type == "url" else None,
        "next_refresh": None,  # Will be calculated based on schedule
        "profile_type": profile_type,  # "outline", "cbk", or None (replaces cissp_type)
        "profile_domain": profile_domain,  # domain identifier string or None (replaces cissp_domain)
        "is_priority_kb": is_priority_kb,  # True for priority/hot topics KB
        "embedding_provider": embedding_provider,  # "openai", "gemini", etc.
        "embedding_model": embedding_model  # specific embedding model or None for provider default
    }
    
    config["knowledge_bases"].append(new_kb)
    save_knowledge_config(config)
    return kb_id

def remove_knowledge_base(kb_id):
    """Remove a knowledge base from the configuration and clean up associated files"""
    import shutil
    
    config = load_knowledge_config()
    
    # Find the knowledge base to be removed
    kb_to_remove = None
    remaining_kbs = []
    
    for kb in config["knowledge_bases"]:
        if kb["id"] == kb_id:
            kb_to_remove = kb
        else:
            remaining_kbs.append(kb)
    
    if kb_to_remove:
        # Clean up files based on knowledge base type
        if kb_to_remove["type"] == "file":
            # Remove the original uploaded file
            try:
                source_path = _resolve_kb_source_path(kb_to_remove.get("source"))
                if source_path and os.path.exists(source_path):
                    os.remove(source_path)
                    print(f"Removed source file: {source_path}")
            except Exception as e:
                print(f"Error removing source file: {e}")
        
        # Remove the knowledge base folder with embeddings (for all types except embedded)
        if kb_to_remove["type"] != "embedded":
            kb_folder = os.path.join(os.path.dirname(__file__), "..", "knowledge_bases", kb_id)
            if os.path.exists(kb_folder):
                try:
                    shutil.rmtree(kb_folder)
                    print(f"Removed knowledge base folder: {kb_folder}")
                except Exception as e:
                    print(f"Error removing knowledge base folder: {e}")
            else:
                print(f"Knowledge base folder not found (already cleaned): {kb_folder}")
        
        # Update configuration
        config["knowledge_bases"] = remaining_kbs
        save_knowledge_config(config)
        
        # Clean up agent references to this knowledge base
        _cleanup_agent_kb_references(kb_id)
        
        print(f"Removed knowledge base: {kb_to_remove['title']} ({kb_id})")
        return True
    
    return False

def _cleanup_agent_kb_references(kb_id):
    """Remove references to deleted knowledge base from all agents"""
    try:
        from app.models.agent import agent_manager
        
        # Get all agents and check if they reference the deleted KB
        agents_updated = 0
        for agent in agent_manager.get_all_agents():
            if kb_id in agent.knowledge_bases:
                # Remove the KB reference from the agent
                agent.knowledge_bases.remove(kb_id)
                agents_updated += 1
        
        # Save the updated agents if any were modified
        if agents_updated > 0:
            agent_manager.save_agents()
            print(f"Cleaned up knowledge base references from {agents_updated} agents")
            
    except Exception as e:
        print(f"Error cleaning up agent KB references: {e}")

def get_active_knowledge_bases():
    """Get all active knowledge bases"""
    config = load_knowledge_config()
    return [kb for kb in config["knowledge_bases"] if kb["status"] == "active"]

def get_knowledge_bases_for_agent(agent_id: str, agent_knowledge_bases: list = None):
    """Get knowledge bases that an agent has access to.
    
    Args:
        agent_id: The ID of the agent
        agent_knowledge_bases: List of knowledge base IDs explicitly assigned to the agent
        
    Returns:
        List of knowledge base configurations that the agent can access.
        Only returns knowledge bases that are explicitly assigned to the agent.
    """
    config = load_knowledge_config()
    all_kbs = [kb for kb in config.get("knowledge_bases", []) if kb.get("status") == "active"]
    
    # If no agent knowledge bases specified, return empty list (no access)
    if not agent_knowledge_bases:
        return []
    
    accessible_kbs = []
    for kb in all_kbs:
        # Only include knowledge bases that are explicitly assigned to the agent
        if kb["id"] in agent_knowledge_bases:
            accessible_kbs.append(kb)
    
    return accessible_kbs

def cleanup_orphaned_kb_references():
    """Clean up any orphaned knowledge base references from agents"""
    try:
        from app.models.agent import agent_manager
        
        # Get all valid KB IDs
        config = load_knowledge_config()
        valid_kb_ids = {kb["id"] for kb in config.get("knowledge_bases", [])}
        
        agents_updated = 0
        total_orphans_removed = 0
        
        for agent in agent_manager.get_all_agents():
            original_kb_count = len(agent.knowledge_bases)
            # Filter out any KB IDs that no longer exist
            agent.knowledge_bases = [kb_id for kb_id in agent.knowledge_bases if kb_id in valid_kb_ids]
            
            orphans_removed = original_kb_count - len(agent.knowledge_bases)
            if orphans_removed > 0:
                agents_updated += 1
                total_orphans_removed += orphans_removed
        
        # Save the updated agents if any were modified
        if agents_updated > 0:
            agent_manager.save_agents()
            print(f"Cleaned up {total_orphans_removed} orphaned KB references from {agents_updated} agents")
            return True
        
        return False
        
    except Exception as e:
        print(f"Error cleaning up orphaned KB references: {e}")
        return False

def cleanup_orphaned_kb_folders():
    """Clean up knowledge base folders that exist in filesystem but not in configuration"""
    import shutil
    
    try:
        # Get all valid KB IDs from the configuration
        config = load_knowledge_config()
        valid_kb_ids = set(kb["id"] for kb in config.get("knowledge_bases", []))
        
        # Check knowledge_bases directory for orphaned folders
        kb_base_dir = os.path.join(os.path.dirname(__file__), "..", "knowledge_bases")
        if os.path.exists(kb_base_dir):
            cleaned_count = 0
            for item in os.listdir(kb_base_dir):
                item_path = os.path.join(kb_base_dir, item)
                
                # Check if it's a directory that looks like a KB ID (starts with "kb_")
                if os.path.isdir(item_path) and item.startswith("kb_") and item not in valid_kb_ids:
                    try:
                        shutil.rmtree(item_path)
                        print(f"Removed orphaned knowledge base folder: {item}")
                        cleaned_count += 1
                    except Exception as e:
                        print(f"Error removing orphaned folder {item}: {e}")
            
            if cleaned_count > 0:
                print(f"Cleaned up {cleaned_count} orphaned knowledge base folders")
                return True
            else:
                print("No orphaned knowledge base folders found")
                return False
                
    except Exception as e:
        print(f"Error cleaning up orphaned KB folders: {e}")
        return False

def full_knowledge_base_cleanup():
    """Perform complete cleanup of orphaned knowledge base data"""
    print("Starting comprehensive knowledge base cleanup...")
    refs_cleaned = cleanup_orphaned_kb_references()
    folders_cleaned = cleanup_orphaned_kb_folders()
    
    if refs_cleaned or folders_cleaned:
        print("Knowledge base cleanup completed - orphaned data removed!")
        return True
    else:
        print("Knowledge base cleanup completed - no orphaned data found.")
        return False

def update_knowledge_base_access(kb_id: str, access_type: str):
    """Update knowledge base access settings"""
    config = load_knowledge_config()
    
    for kb in config.get("knowledge_bases", []):
        if kb["id"] == kb_id:
            kb["access_type"] = access_type
            save_knowledge_config(config)
            return True
    
    return False


def export_knowledge_base(kb_id: str, include_embeddings: bool = True) -> tuple[bool, str, Optional[bytes]]:
    """
    Export a knowledge base as a ZIP package.
    
    Args:
        kb_id: Knowledge base identifier to export
        include_embeddings: Whether to include processed embeddings
        
    Returns:
        Tuple of (success, message, zip_bytes)
    """
    from io import BytesIO
    
    # Load KB config
    config = load_knowledge_config()
    kb_config = None
    for kb in config.get("knowledge_bases", []):
        if kb.get("id") == kb_id:
            kb_config = kb
            break
    
    if not kb_config:
        return False, "Knowledge base not found", None
    
    # Locate source file
    stored_source_path = kb_config.get("source")
    source_path = _resolve_kb_source_path(stored_source_path)
    if not source_path:
        missing_source = stored_source_path or "(empty)"
        return False, f"Source file not found: {missing_source}", None

    # Keep persisted source OS-agnostic and normalized during export flows too.
    normalized_source = _normalize_kb_source_for_storage(source_path)
    if normalized_source and normalized_source != kb_config.get("source"):
        kb_config["source"] = normalized_source
        save_knowledge_config(config)
    
    # Locate processed folder
    kb_base_dir = os.path.join(os.path.dirname(__file__), "..", "knowledge_bases")
    processed_folder = os.path.join(kb_base_dir, kb_id)
    
    # Prepare manifest
    original_filename = os.path.basename(source_path)
    
    # Get embedding dimensions
    embeddings_path = os.path.join(processed_folder, "embeddings.npy")
    dimensions = None
    chunk_count = None
    
    if os.path.exists(embeddings_path):
        import numpy as np
        try:
            embeddings = np.load(embeddings_path)
            dimensions = embeddings.shape[1] if len(embeddings.shape) > 1 else len(embeddings)
            chunk_count = embeddings.shape[0] if len(embeddings.shape) > 0 else 1
        except:
            pass
    
    manifest = {
        "title": kb_config.get("title"),
        "description": kb_config.get("description"),
        "kb_type": kb_config.get("type"),
        "source_filename": original_filename,
        "source_relative_path": kb_config.get("source"),
        "exam_profile_ids": kb_config.get("exam_profile_ids", []),
        "profile_type": kb_config.get("profile_type"),
        "profile_domain": kb_config.get("profile_domain"),
        "is_priority_kb": kb_config.get("is_priority_kb", False),
        "access_type": kb_config.get("access_type", "shared"),
        "category": kb_config.get("category", "general"),
        "embedding_info": {
            "provider": kb_config.get("embedding_provider", "openai"),
            "model": kb_config.get("embedding_model"),
            "dimensions": dimensions,
            "chunk_count": chunk_count
        },
        "export_metadata": {
            "export_version": "1.0",
            "export_timestamp": datetime.now().isoformat(),
            "has_embeddings": include_embeddings and os.path.exists(processed_folder)
        }
    }
    
    # Create ZIP in memory
    zip_buffer = BytesIO()
    
    try:
        checksums: Dict[str, str] = {}
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Add source file
            zipf.write(source_path, f'source/{original_filename}')
            source_checksum = _sha256_for_file(source_path)
            if source_checksum:
                checksums[f"source/{original_filename}"] = source_checksum
            
            # Add processed files if requested and available
            if include_embeddings and os.path.exists(processed_folder):
                for filename in [CHUNKS_JSON_GZ, LEGACY_CHUNKS_GZ, 'embeddings.npy', 'index.faiss']:
                    file_path = os.path.join(processed_folder, filename)
                    if os.path.exists(file_path):
                        archive_name = f'processed/{filename}'
                        zipf.write(file_path, archive_name)
                        checksum = _sha256_for_file(file_path)
                        if checksum:
                            checksums[archive_name] = checksum

            # Add manifest last so checksums capture all artifacts.
            manifest["file_checksums"] = checksums
            zipf.writestr('manifest.json', json.dumps(manifest, indent=2, ensure_ascii=False))
        
        zip_buffer.seek(0)
        return True, "Knowledge base exported successfully", zip_buffer.getvalue()
    
    except Exception as e:
        return False, f"Export failed: {str(e)}", None


def import_knowledge_base(zip_file, user_embedding_provider: str, user_embedding_model: str = None) -> tuple[bool, str, List[str], Optional[str]]:
    """
    Import a knowledge base from ZIP package.
    
    Args:
        zip_file: Uploaded ZIP file object
        user_embedding_provider: Current user's embedding provider
        user_embedding_model: Current user's embedding model (optional)
        
    Returns:
        Tuple of (success, message, warnings, new_kb_id)
    """
    warnings = []
    temp_dir = None
    
    try:
        is_valid_zip, validation_message = _validate_zip_integrity(zip_file)
        if not is_valid_zip:
            return False, f"Invalid package: {validation_message}", [], None

        # Create temp directory for extraction
        temp_dir = tempfile.mkdtemp()
        
        # Extract ZIP safely
        extracted, extract_message = _extract_zip_safely(zip_file, temp_dir)
        if not extracted:
            return False, f"Invalid package: {extract_message}", [], None
        
        # Read manifest
        manifest_path = os.path.join(temp_dir, 'manifest.json')
        if not os.path.exists(manifest_path):
            return False, "Invalid package: manifest.json not found", [], None
        
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)

        # Validate checksums if present
        expected_checksums = manifest.get("file_checksums", {})
        if isinstance(expected_checksums, dict):
            for archive_name, expected_digest in expected_checksums.items():
                if not isinstance(archive_name, str) or not isinstance(expected_digest, str):
                    continue
                actual_path = _safe_member_path(temp_dir, archive_name)
                if not actual_path or not os.path.exists(actual_path):
                    warnings.append(f"Missing file for checksum validation: {archive_name}")
                    continue
                actual_digest = _sha256_for_file(actual_path)
                if actual_digest != expected_digest:
                    return False, f"Invalid package: checksum mismatch for {archive_name}", [], None
        
        # Validate required fields
        required_fields = ["title", "description", "kb_type", "source_filename"]
        for field in required_fields:
            if field not in manifest:
                return False, f"Invalid manifest: missing field '{field}'", [], None
        
        # Check embedding compatibility
        manifest_provider = manifest.get("embedding_info", {}).get("provider", "openai")
        manifest_model = manifest.get("embedding_info", {}).get("model")
        has_embeddings = manifest.get("export_metadata", {}).get("has_embeddings", False)
        
        can_reuse_embeddings = (
            has_embeddings and 
            manifest_provider == user_embedding_provider and
            (not user_embedding_model or manifest_model == user_embedding_model or not manifest_model)
        )
        
        if has_embeddings and not can_reuse_embeddings:
            warnings.append(f"Embedding provider mismatch ({manifest_provider} -> {user_embedding_provider}) - will re-process (2-5 minutes)")
        
        # Validate exam profile IDs
        exam_profile_ids = manifest.get("exam_profile_ids", [])
        if exam_profile_ids:
            from app.config.exam_profile_config import profile_exists
            valid_profile_ids = [pid for pid in exam_profile_ids if profile_exists(pid)]
            invalid_profiles = [pid for pid in exam_profile_ids if not profile_exists(pid)]
            
            if invalid_profiles:
                warnings.append(f"Exam profiles not found: {', '.join(invalid_profiles)}")
            
            exam_profile_ids = valid_profile_ids
        
        # Generate new KB ID
        config = load_knowledge_config()
        new_kb_id = f"kb_{len(config['knowledge_bases'])}_{int(datetime.now().timestamp())}"
        
        # Copy source file
        source_filename = manifest["source_filename"]
        source_temp_path = os.path.join(temp_dir, 'source', source_filename)
        
        if not os.path.exists(source_temp_path):
            return False, "Source file not found in package", [], None
        
        kb_base_dir = os.path.join(os.path.dirname(__file__), "..", "knowledge_bases")
        os.makedirs(kb_base_dir, exist_ok=True)
        
        # Create unique filename for source
        base_name, ext = os.path.splitext(source_filename)
        new_source_path = os.path.join(kb_base_dir, f"{base_name}_{int(datetime.now().timestamp())}{ext}")
        shutil.copy2(source_temp_path, new_source_path)
        stored_source_path = _normalize_kb_source_for_storage(new_source_path)
        
        # Handle embeddings
        new_processed_folder = os.path.join(kb_base_dir, new_kb_id)
        
        if can_reuse_embeddings:
            # Copy processed files
            os.makedirs(new_processed_folder, exist_ok=True)
            processed_temp_path = os.path.join(temp_dir, 'processed')

            safe_reuse_files = [CHUNKS_JSON_GZ, 'embeddings.npy', 'index.faiss']
            if not os.path.exists(os.path.join(processed_temp_path, CHUNKS_JSON_GZ)):
                can_reuse_embeddings = False
                warnings.append("Package does not contain JSON chunks; reprocessing required")
            else:
                for filename in safe_reuse_files:
                    src = os.path.join(processed_temp_path, filename)
                    dst = os.path.join(new_processed_folder, filename)
                    if os.path.exists(src):
                        if os.path.getsize(src) > MAX_IMPORT_MEMBER_BYTES:
                            return False, f"Invalid package: {filename} exceeds size limit", [], None
                        shutil.copy2(src, dst)
            
                embedding_status = "completed"
                warnings.append(f"Reused embeddings from package (provider: {manifest_provider})")
        if not can_reuse_embeddings:
            # Will need to re-process
            embedding_status = "pending"
            if not has_embeddings:
                warnings.append("No embeddings in package - will process with your provider")
        
        # Create KB entry
        new_kb = {
            "id": new_kb_id,
            "title": manifest["title"],
            "description": manifest["description"],
            "type": manifest["kb_type"],
            "source": stored_source_path,
            "chunks_path": None,
            "created_at": datetime.now().isoformat(),
            "exam_profile_ids": exam_profile_ids,
            "status": "active",
            "access_type": manifest.get("access_type", "shared"),
            "category": manifest.get("category", "general"),
            "refresh_schedule": "manual",
            "last_refreshed": None,
            "next_refresh": None,
            "profile_type": manifest.get("profile_type"),
            "profile_domain": manifest.get("profile_domain"),
            "is_priority_kb": manifest.get("is_priority_kb", False),
            "embedding_provider": user_embedding_provider,
            "embedding_model": user_embedding_model,
            "embedding_status": embedding_status
        }
        
        config["knowledge_bases"].append(new_kb)
        save_knowledge_config(config)
        
        # Trigger processing if needed
        if not can_reuse_embeddings:
            from app.utils.knowledge_processor import process_knowledge_base
            update_embedding_status(new_kb_id, "processing")
            
            # Determine processor type
            processor_type = "pdf" if manifest["kb_type"] == "document" and source_filename.lower().endswith('.pdf') else "file"
            
            success, _ = process_knowledge_base(
                new_kb_id, 
                processor_type, 
                new_source_path,
                generate_summary=False,
                embedding_provider=user_embedding_provider
            )
            
            if success:
                update_embedding_status(new_kb_id, "completed")
                warnings.append(f"Successfully processed with {user_embedding_provider}")
            else:
                update_embedding_status(new_kb_id, "failed")
                warnings.append("Processing failed - check logs")
        
        return True, "Knowledge base imported successfully", warnings, new_kb_id
    
    except Exception as e:
        return False, f"Import failed: {str(e)}", [], None
    
    finally:
        # Cleanup temp directory
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except:
                pass