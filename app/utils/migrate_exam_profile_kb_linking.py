"""
Migration Script: Add exam_profile_id to Knowledge Bases

This script migrates existing knowledge bases to add the exam_profile_id field.
KBs with profile_type or profile_domain are linked to cissp_2024.
KBs without these fields remain general (exam_profile_id = null).
"""

import json
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.config.knowledge_config import KNOWLEDGE_CONFIG_PATH


def migrate_kb_exam_profile_linking():
    """Add exam_profile_id field to all knowledge bases"""
    
    print("[INFO] Starting KB exam profile migration...")
    
    if not os.path.exists(KNOWLEDGE_CONFIG_PATH):
        print("[ERROR] knowledge_bases.json not found")
        return False
    
    # Load current config
    with open(KNOWLEDGE_CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    
    kbs = config.get("knowledge_bases", [])
    migrated_count = 0
    already_migrated = 0
    
    for kb in kbs:
        # Check if already has exam_profile_id field
        if "exam_profile_id" in kb:
            already_migrated += 1
            continue
        
        # Check if KB has CISSP-related fields
        has_profile_type = kb.get("profile_type") or kb.get("cissp_type")
        has_profile_domain = kb.get("profile_domain") or kb.get("cissp_domain")
        
        if has_profile_type or has_profile_domain:
            # Link to CISSP profile
            kb["exam_profile_id"] = "cissp_2024"
            print(f"[MIGRATED] {kb.get('title', 'Unknown')} -> cissp_2024")
        else:
            # General KB (no profile)
            kb["exam_profile_id"] = None
            print(f"[GENERAL] {kb.get('title', 'Unknown')} -> no profile")
        
        migrated_count += 1
    
    # Save updated config
    with open(KNOWLEDGE_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    
    print(f"\n[SUMMARY]")
    print(f"  Migrated: {migrated_count} KBs")
    print(f"  Already migrated: {already_migrated} KBs")
    print(f"  Total: {len(kbs)} KBs")
    print(f"\n[SUCCESS] Migration completed successfully!")
    
    return True


if __name__ == "__main__":
    success = migrate_kb_exam_profile_linking()
    sys.exit(0 if success else 1)
