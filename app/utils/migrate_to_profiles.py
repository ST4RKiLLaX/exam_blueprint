"""
Migration Script: Convert CISSP-specific data to Exam Profiles

This script migrates existing agents and knowledge bases from the hardcoded
CISSP system to the new exam profile system.

Run this script once after deploying the profile system changes.
"""

import json
import os
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

AGENTS_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "agents.json")
KNOWLEDGE_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "knowledge_bases.json")


def migrate_agents():
    """Migrate agents from enable_cissp_mode to exam_profile_id"""
    
    if not os.path.exists(AGENTS_PATH):
        print("[INFO] No agents.json found, skipping agent migration")
        return
    
    try:
        with open(AGENTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        print("[ERROR] Could not load agents.json")
        return
    
    agents = data.get("agents", {})
    migrated_count = 0
    
    for agent_id, agent_data in agents.items():
        # Check if agent has enable_cissp_mode set to True
        if agent_data.get("enable_cissp_mode", False):
            # Set exam_profile_id if not already set
            if "exam_profile_id" not in agent_data or agent_data["exam_profile_id"] is None:
                agent_data["exam_profile_id"] = "cissp_2024"
                migrated_count += 1
                print(f"[MIGRATE] Agent '{agent_data.get('name', agent_id)}': enable_cissp_mode=True -> exam_profile_id='cissp_2024'")
        else:
            # Ensure exam_profile_id is None for agents without CISSP mode
            if "exam_profile_id" not in agent_data:
                agent_data["exam_profile_id"] = None
    
    # Save migrated agents
    if migrated_count > 0:
        with open(AGENTS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"[SUCCESS] Migrated {migrated_count} agent(s) to exam profiles")
    else:
        print("[INFO] No agents needed migration (already using exam_profile_id)")


def migrate_knowledge_bases():
    """Migrate KBs: cissp_type → profile_type, cissp_domain → profile_domain, add is_priority_kb"""
    
    if not os.path.exists(KNOWLEDGE_PATH):
        print("[INFO] No knowledge.json found, skipping KB migration")
        return
    
    try:
        with open(KNOWLEDGE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        print("[ERROR] Could not load knowledge.json")
        return
    
    kbs = data.get("knowledge_bases", [])
    migrated_count = 0
    
    for kb in kbs:
        changed = False
        
        # Rename cissp_type → profile_type
        if "cissp_type" in kb:
            if "profile_type" not in kb:
                kb["profile_type"] = kb["cissp_type"]
                changed = True
            # Keep cissp_type for backward compatibility during transition
        
        # Rename cissp_domain → profile_domain
        if "cissp_domain" in kb:
            if "profile_domain" not in kb:
                kb["profile_domain"] = kb["cissp_domain"]
                changed = True
            # Keep cissp_domain for backward compatibility during transition
        
        # Add is_priority_kb field (detect "golden" in title)
        if "is_priority_kb" not in kb:
            title = kb.get("title", "").lower()
            kb["is_priority_kb"] = "golden" in title
            if kb["is_priority_kb"]:
                print(f"[MIGRATE] KB '{kb.get('title', kb.get('id'))}': detected as priority KB")
            changed = True
        
        if changed:
            migrated_count += 1
            print(f"[MIGRATE] KB '{kb.get('title', kb.get('id'))}': updated profile fields")
    
    # Save migrated KBs
    if migrated_count > 0:
        with open(KNOWLEDGE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"[SUCCESS] Migrated {migrated_count} knowledge base(s) to exam profiles")
    else:
        print("[INFO] No knowledge bases needed migration (already using profile fields)")


def verify_migration():
    """Verify migration completed successfully"""
    
    print("\n[VERIFY] Checking migration results...")
    
    # Check agents
    if os.path.exists(AGENTS_PATH):
        try:
            with open(AGENTS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            agents = data.get("agents", {})
            
            cissp_agents = sum(1 for a in agents.values() if a.get("exam_profile_id") == "cissp_2024")
            print(f"[VERIFY] Found {cissp_agents} agent(s) with CISSP profile")
        except Exception as e:
            print(f"[ERROR] Could not verify agents: {e}")
    
    # Check KBs
    if os.path.exists(KNOWLEDGE_PATH):
        try:
            with open(KNOWLEDGE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            kbs = data.get("knowledge_bases", [])
            
            profile_kbs = sum(1 for kb in kbs if "profile_type" in kb or "profile_domain" in kb)
            priority_kbs = sum(1 for kb in kbs if kb.get("is_priority_kb", False))
            print(f"[VERIFY] Found {profile_kbs} KB(s) with profile fields")
            print(f"[VERIFY] Found {priority_kbs} priority KB(s)")
        except Exception as e:
            print(f"[ERROR] Could not verify KBs: {e}")
    
    print("\n[DONE] Migration verification complete")


def main():
    """Run all migration tasks"""
    
    print("=" * 60)
    print("EXAM PROFILE SYSTEM MIGRATION")
    print("=" * 60)
    print(f"Started: {datetime.now().isoformat()}\n")
    
    # Migrate agents
    print("[STEP 1/3] Migrating agents...")
    migrate_agents()
    print()
    
    # Migrate knowledge bases
    print("[STEP 2/3] Migrating knowledge bases...")
    migrate_knowledge_bases()
    print()
    
    # Verify migration
    print("[STEP 3/3] Verifying migration...")
    verify_migration()
    print()
    
    print("=" * 60)
    print(f"Completed: {datetime.now().isoformat()}")
    print("=" * 60)
    print("\n[INFO] Migration complete! Restart the Flask server to use the new profile system.")


if __name__ == "__main__":
    main()
