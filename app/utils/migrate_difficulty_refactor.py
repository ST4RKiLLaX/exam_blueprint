"""
Migration Script: Old Difficulty Levels to New Three-Layer System

This script migrates exam profiles from the old difficulty system (where levels
were stored per-profile with full definitions) to the new three-layer system
(global levels → question types tagged with levels → profile settings).

Usage:
    python -m app.utils.migrate_difficulty_refactor

Backup:
    Creates backup file: exam_profiles.json.backup_<timestamp>
"""

import json
import os
import shutil
from datetime import datetime
from typing import Dict, List, Any


def backup_profiles():
    """Create a timestamped backup of exam_profiles.json"""
    profiles_path = os.path.join(
        os.path.dirname(__file__), 
        '..', 
        'config', 
        'exam_profiles.json'
    )
    
    if not os.path.exists(profiles_path):
        print("[WARN] exam_profiles.json not found - nothing to backup")
        return None
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{profiles_path}.backup_{timestamp}"
    
    shutil.copy2(profiles_path, backup_path)
    print(f"[INFO] Backup created: {backup_path}")
    
    return backup_path


def analyze_question_type_phrase(phrase: str) -> str:
    """
    Heuristically determine difficulty level from question type phrase.
    
    Level 1 (Recall): definition, identify, recognize, TRUE about, stands for
    Level 2 (Application): scenario, apply, troubleshoot, determine, cause
    Level 3 (Evaluation): BEST, MOST, PRIMARY, FIRST, NOT apply
    
    Args:
        phrase: Question type phrase
        
    Returns:
        Level ID string ("1", "2", or "3")
    """
    phrase_lower = phrase.lower()
    
    # Level 1 indicators (Recall/Knowledge)
    level_1_indicators = [
        'definition', 'define', 'identify', 'recognize', 
        'true about', 'stands for', 'is an example of',
        'what is', 'which statement is true'
    ]
    
    # Level 2 indicators (Application/Analysis)
    level_2_indicators = [
        'in this scenario', 'what should you do', 'apply',
        'determine', 'troubleshoot', 'cause of', 'analyze',
        'classify', 'which principle applies'
    ]
    
    # Level 3 indicators (Evaluation/Judgment)
    level_3_indicators = [
        'best', 'most', 'primary', 'first', 'not apply',
        'would not', 'exception', 'evaluate', 'prioritize',
        'choose', 'which control', 'most effective'
    ]
    
    # Check in order of specificity (3 → 2 → 1)
    for indicator in level_3_indicators:
        if indicator in phrase_lower:
            return "3"
    
    for indicator in level_2_indicators:
        if indicator in phrase_lower:
            return "2"
    
    for indicator in level_1_indicators:
        if indicator in phrase_lower:
            return "1"
    
    # Default: assume Level 3 (most conservative - evaluation/judgment)
    return "3"


def migrate_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migrate a single profile to the new difficulty system.
    
    Changes:
    1. Tag all question types with difficulty_level field
    2. Create difficulty_profile section with weights and display names
    3. Remove old difficulty_levels array
    
    Args:
        profile: Profile dictionary
        
    Returns:
        Migrated profile dictionary
    """
    profile_id = profile.get('profile_id', 'unknown')
    print(f"\n[INFO] Migrating profile: {profile_id}")
    
    # 1. Tag question types with difficulty levels
    question_types = profile.get('question_types', [])
    
    for qt in question_types:
        if 'difficulty_level' not in qt:
            # Use heuristic to determine level from phrase
            phrase = qt.get('phrase', '')
            inferred_level = analyze_question_type_phrase(phrase)
            qt['difficulty_level'] = inferred_level
            print(f"  - Tagged question type '{qt.get('id')}' as Level {inferred_level} (inferred from phrase)")
    
    # 2. Create default difficulty_profile
    if 'difficulty_profile' not in profile:
        # Determine which levels actually have question types assigned
        levels_with_types = set()
        for qt in question_types:
            level = qt.get('difficulty_level')
            if level:
                levels_with_types.add(level)
        
        # Only enable levels that have question types (sorted for consistency)
        enabled_levels = sorted(list(levels_with_types))
        
        if not enabled_levels:
            # Fallback: if no question types exist, enable all levels
            enabled_levels = ['1', '2', '3']
            print(f"  - No question types found, enabling all levels by default")
        else:
            print(f"  - Enabling only levels with question types: {enabled_levels}")
        
        # Calculate equal weights for enabled levels
        num_enabled = len(enabled_levels)
        base_weight = 1.0 / num_enabled
        weights = {}
        for i, level_id in enumerate(['1', '2', '3']):
            if level_id in enabled_levels:
                # Add remainder to last enabled level for exact 1.0 sum
                if i == len(['1', '2', '3']) - 1:
                    weights[level_id] = 1.0 - sum(weights.values())
                else:
                    weights[level_id] = round(base_weight, 2)
            else:
                weights[level_id] = 0.0
        
        # Preserve custom display names from old difficulty_levels if they exist
        display_names = {
            '1': 'Level 1',
            '2': 'Level 2',
            '3': 'Level 3'
        }
        
        if 'difficulty_levels' in profile:
            old_levels = profile['difficulty_levels']
            for old_level in old_levels:
                level_id = old_level.get('level_id')
                if level_id in ['1', '2', '3']:
                    display_names[level_id] = old_level.get('name', f'Level {level_id}')
                    print(f"  - Preserved display name for Level {level_id}: '{display_names[level_id]}'")
        
        # Create difficulty_profile
        profile['difficulty_profile'] = {
            'enabled_levels': enabled_levels,
            'weights': weights,
            'display_names': display_names
        }
        print(f"  - Created difficulty_profile with weights: {weights}")
    else:
        print(f"  - difficulty_profile already exists (skipping)")
    
    # 3. Remove old difficulty_levels array
    if 'difficulty_levels' in profile:
        del profile['difficulty_levels']
        print(f"  - Removed old difficulty_levels array")
    
    return profile


def migrate_all_profiles():
    """
    Migrate all exam profiles to new difficulty system.
    
    Returns:
        Tuple of (success, message)
    """
    profiles_path = os.path.join(
        os.path.dirname(__file__), 
        '..', 
        'config', 
        'exam_profiles.json'
    )
    
    if not os.path.exists(profiles_path):
        return False, "exam_profiles.json not found"
    
    # Create backup
    backup_path = backup_profiles()
    
    # Load profiles
    try:
        with open(profiles_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        return False, f"Failed to load profiles: {str(e)}"
    
    profiles = config.get('profiles', [])
    
    if not profiles:
        print("[INFO] No profiles found to migrate")
        return True, "No profiles to migrate"
    
    # Migrate each profile
    print(f"[INFO] Found {len(profiles)} profile(s) to migrate")
    
    migrated_count = 0
    for profile in profiles:
        try:
            migrate_profile(profile)
            migrated_count += 1
        except Exception as e:
            profile_id = profile.get('profile_id', 'unknown')
            print(f"[ERROR] Failed to migrate profile '{profile_id}': {str(e)}")
            # Continue with other profiles
    
    # Save migrated profiles
    try:
        with open(profiles_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        print(f"\n[SUCCESS] Successfully migrated {migrated_count}/{len(profiles)} profiles")
        print(f"[INFO] Migrated profiles saved to: {profiles_path}")
        
        if backup_path:
            print(f"[INFO] Backup available at: {backup_path}")
        
        return True, f"Successfully migrated {migrated_count} profiles"
        
    except Exception as e:
        return False, f"Failed to save migrated profiles: {str(e)}"


def rollback_migration(backup_path: str):
    """
    Rollback migration by restoring from backup.
    
    Args:
        backup_path: Path to backup file
        
    Returns:
        Tuple of (success, message)
    """
    if not os.path.exists(backup_path):
        return False, f"Backup file not found: {backup_path}"
    
    profiles_path = os.path.join(
        os.path.dirname(__file__), 
        '..', 
        'config', 
        'exam_profiles.json'
    )
    
    try:
        shutil.copy2(backup_path, profiles_path)
        return True, f"Successfully rolled back to: {backup_path}"
    except Exception as e:
        return False, f"Failed to rollback: {str(e)}"


if __name__ == '__main__':
    print("=" * 70)
    print("Exam Profile Difficulty System Migration")
    print("=" * 70)
    print("\nThis script will migrate exam profiles from the old difficulty system")
    print("to the new three-layer architecture.")
    print("\nChanges:")
    print("  1. Add 'difficulty_level' field to each question_type")
    print("  2. Create 'difficulty_profile' section with weights and display names")
    print("  3. Remove old 'difficulty_levels' array")
    print("\nA backup will be created automatically.")
    print("=" * 70)
    
    response = input("\nProceed with migration? (yes/no): ").strip().lower()
    
    if response != 'yes':
        print("\n[CANCELLED] Migration cancelled by user")
        exit(0)
    
    print("\n[INFO] Starting migration...")
    success, message = migrate_all_profiles()
    
    if success:
        print(f"\n✓ {message}")
        exit(0)
    else:
        print(f"\n✗ Migration failed: {message}")
        exit(1)
