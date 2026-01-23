"""
Migration Script: Convert KB exam_profile_id to exam_profile_ids

This script migrates existing knowledge bases from single exam_profile_id
to multi-profile exam_profile_ids array format.

Run once after updating to multi-profile support.
"""

import json
import os
from datetime import datetime


def migrate_kb_to_multi_profile():
    """Migrate knowledge_bases.json to use exam_profile_ids arrays"""
    
    kb_config_path = os.path.join(
        os.path.dirname(__file__), "..", "config", "knowledge_bases.json"
    )
    
    if not os.path.exists(kb_config_path):
        print("No knowledge_bases.json found - nothing to migrate")
        return
    
    # Load current config
    with open(kb_config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    
    kbs = config.get("knowledge_bases", [])
    migrated_count = 0
    
    for kb in kbs:
        # Check if already migrated (has exam_profile_ids)
        if "exam_profile_ids" in kb:
            continue
        
        # Migrate exam_profile_id to exam_profile_ids
        old_profile_id = kb.get("exam_profile_id")
        
        if old_profile_id:
            kb["exam_profile_ids"] = [old_profile_id]
            print(f"Migrated KB '{kb.get('title')}': '{old_profile_id}' -> [{old_profile_id}]")
        else:
            kb["exam_profile_ids"] = []
            print(f"Migrated KB '{kb.get('title')}': None -> []")
        
        # Remove old field
        kb.pop("exam_profile_id", None)
        migrated_count += 1
    
    # Save updated config
    if migrated_count > 0:
        # Backup original
        backup_path = kb_config_path + f".backup_{int(datetime.now().timestamp())}"
        with open(backup_path, "w", encoding="utf-8") as f:
            # Write the original config to backup before migrating
            f.seek(0)
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        print(f"\nBackup created: {backup_path}")
        
        # Write migrated config
        with open(kb_config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        print(f"\n[OK] Migration complete: {migrated_count} KB(s) migrated")
        print(f"     Knowledge bases now support multiple exam profiles")
    else:
        print("\n[OK] No migration needed - all KBs already use exam_profile_ids")


if __name__ == "__main__":
    migrate_kb_to_multi_profile()
