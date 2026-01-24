---
name: Refactor Difficulty Levels Architecture
overview: "Refactor the difficulty levels system from a profile-specific feature to a three-layer architecture: global canonical levels, exam-specific question types tagged with difficulty, and profile-specific weights/display names. This eliminates the cognitive dissonance between question type phrasing and difficulty constraints."
todos:
  - id: phase1-global-config
    content: Create app/config/difficulty_config.py with GLOBAL_DIFFICULTY_LEVELS and helper functions
    status: completed
  - id: phase2-profile-schema
    content: "Update exam_profile_config.py: remove old CRUD functions, add difficulty_profile functions, update validation"
    status: completed
  - id: phase3-blueprint-logic
    content: "Refactor reasoning_controller.py: replace select_difficulty_level with select_question_type_with_difficulty, update select_blueprint"
    status: completed
  - id: phase4-prompt-building
    content: Update agent.py build_prompt to get difficulty from question type and use global level descriptions
    status: completed
  - id: phase5-api-endpoints
    content: "Update server.py: remove old difficulty API endpoints, add new difficulty_settings endpoints"
    status: completed
  - id: phase6-profile-editor-ui
    content: "Refactor exam_profiles.html: remove Difficulty Levels tab, add difficulty settings section, update question types UI"
    status: completed
  - id: phase7-test-interface
    content: "Update test.html: use custom display names in checkboxes, show question type counts per level"
    status: completed
  - id: phase8-example-profile
    content: "Update exam_profile_example.json: add difficulty_level to question types, add difficulty_profile section, remove old difficulty_levels"
    status: completed
  - id: phase9-migration
    content: Create migrate_difficulty_refactor.py script to convert existing profiles
    status: completed
  - id: testing
    content: "Test the refactored system: unit tests, integration tests, manual testing with CISSP profile"
    status: completed
isProject: false
---

# Difficulty Levels Architecture Refactor

## Problem Statement

Currently, difficulty levels and question types are independent dimensions, causing cognitive conflicts. Question types like "Which is BEST?" inherently signal Level 3 (Evaluation/Judgment) difficulty, but the system tries to apply Level 1 or 2 constraints to them, resulting in contradictory AI instructions.

**Result**: System generates only Level 3 questions even when Level 1 or 2 are selected, because the question type phrases override the difficulty constraint.

## Critical Fixes Applied

This plan incorporates essential architectural improvements:

1. **No hardcoded "3 levels"** - System uses OrderedDict and validates any level ID (supports future Level 0, Level 4, etc.)
2. **Runtime weight normalization** - Weights auto-adjust when levels are disabled (prevents distribution errors)
3. **Two-stage selection** - Pick level by weights first, then question type within level (prevents type-count bias)
4. **Comprehensive validation** - 8 validation rules ensure data integrity
5. **Clear prompt hierarchy** - Question type is primary, difficulty is supporting (no conflicts)
6. **Complete API metadata** - Response includes 6 fields for rich UI/analytics

## Solution Architecture

Implement a **three-layer model**:

### Layer 1: Global Difficulty Standards

A canonical set of difficulty levels with cognitive verbs, stored in code. The system ships with three levels (1, 2, 3) but is designed to support any level IDs for future extensibility (e.g., Level 0 for intro, Level 4 for synthesis).

```python
# app/config/difficulty_config.py (NEW FILE)
from collections import OrderedDict

# Global canonical difficulty levels (extensible - not hardcoded to 3 levels)
GLOBAL_DIFFICULTY_LEVELS = OrderedDict([
    ("1", {
        "level_id": "1",
        "name": "Recall / Understanding",
        "verbs": ["define", "identify", "recognize", "list", "state"],
        "description": "Tests memorization and recognition of facts, terms, concepts, and basic definitions."
    }),
    ("2", {
        "level_id": "2",
        "name": "Application / Analysis",
        "verbs": ["apply", "analyze", "determine", "troubleshoot", "classify"],
        "description": "Tests ability to apply knowledge to realistic scenarios and analyze situations."
    }),
    ("3", {
        "level_id": "3",
        "name": "Evaluation / Judgment",
        "verbs": ["prioritize", "evaluate", "choose best", "decide first", "justify"],
        "description": "Tests ability to evaluate options and make professional judgments."
    })
])

def get_global_levels() -> OrderedDict:
    """Get all global difficulty levels"""
    return GLOBAL_DIFFICULTY_LEVELS

def get_level_by_id(level_id: str) -> Optional[Dict]:
    """Get a specific level by ID"""
    return GLOBAL_DIFFICULTY_LEVELS.get(level_id)

def validate_difficulty_level_reference(level_id: str) -> bool:
    """Validate that a level ID exists in global registry"""
    return level_id in GLOBAL_DIFFICULTY_LEVELS

def get_all_level_ids() -> List[str]:
    """Get list of all valid level IDs"""
    return list(GLOBAL_DIFFICULTY_LEVELS.keys())
```

### Layer 2: Question Types Tagged with Difficulty

Each exam profile's question types declare their cognitive level:

```json
"question_types": [
  {
    "id": "definition",
    "difficulty_level": "1",  // References global level
    "phrase": "What is the definition of",
    "guidance": "Test direct recall..."
  },
  {
    "id": "comparative",
    "difficulty_level": "3",  // References global level
    "phrase": "Which is BEST/MOST appropriate?",
    "guidance": "Frame answers as competing options..."
  }
]
```

### Layer 3: Profile Difficulty Settings

Each exam profile configures weights, enabled levels, and display names:

```json
"difficulty_profile": {
  "enabled_levels": ["1", "2", "3"],
  "weights": {
    "1": 0.10,  // 10% Level 1 questions
    "2": 0.35,  // 35% Level 2 questions
    "3": 0.55   // 55% Level 3 questions
  },
  "display_names": {
    "1": "Foundational Knowledge",
    "2": "Scenario Application",
    "3": "Professional Judgment"
  }
}
```

---

## Key Design Principles

These principles address critical architectural requirements:

### 1. No Hardcoded Level Assumptions

- Global levels stored as `OrderedDict`, not list
- Validation works with any level IDs (not just 1, 2, 3)
- System supports Level 0 (intro) or Level 4 (synthesis) without refactoring
- UI generates controls dynamically from global levels API

### 2. Runtime Weight Normalization

- Weights in config don't need to sum to 1.0
- When levels are disabled, weights automatically renormalize among enabled levels
- Example: Disable Level 1 with weights {1: 0.10, 2: 0.35, 3: 0.55}
  - Runtime: {2: 0.39, 3: 0.61} (normalized from remaining)
- Prevents incorrect distributions when toggling levels

### 3. Two-Stage Selection Algorithm

- **Stage 1**: Pick difficulty level using profile weights (normalized for enabled levels only)
- **Stage 2**: Pick question type within selected level using LRU rotation
- **Why?** Prevents one level with many question types from dominating
- Weights control level frequency, not question type frequency
- Makes weight settings predictable for users

### 4. Comprehensive Validation

- Each `question_type.difficulty_level` must exist in global registry
- `enabled_levels` must be subset of global level IDs
- All enabled levels must have at least one question type
- Weights must be numeric, non-negative, and include all enabled levels
- At least one level must be enabled

### 5. Clear Prompt Hierarchy

- **Question type phrase + guidance = PRIMARY** instruction
- **Difficulty level block = SUPPORTING** context
- Never suggest difficulty block overrides question type
- Avoids cognitive conflict in AI instructions

### 6. Complete API Metadata

- Response includes: `question_type_id`, `question_type_phrase`, `difficulty_level_id`, `difficulty_level_display_name`, `difficulty_level_global_name`
- Enables rich UI feedback and analytics
- Frontend can display both profile-specific and global names

---

## Implementation Plan

### Phase 1: Create Global Difficulty Config

**File**: [`app/config/difficulty_config.py`](app/config/difficulty_config.py) (NEW)

Create new file with:

- `GLOBAL_DIFFICULTY_LEVELS` constant (OrderedDict - extensible, not hardcoded to 3)
- `get_global_levels()` - returns all levels as OrderedDict
- `get_level_by_id(level_id)` - gets specific level or None
- `validate_difficulty_level_reference(level_id)` - checks if level exists globally
- `get_all_level_ids()` - returns list of valid level IDs

**Important**: The system ships with levels 1, 2, 3 but the code must not assume only these exist. Future profiles may use Level 0 (intro) or Level 4 (synthesis/design).

### Phase 2: Update Exam Profile Schema

**File**: [`app/config/exam_profile_config.py`](app/config/exam_profile_config.py)

Changes needed:

1. **Remove old difficulty level CRUD functions** (lines 459-646):

   - Delete `get_profile_difficulty_levels()`
   - Delete `add_difficulty_level()`
   - Delete `update_difficulty_level()`
   - Delete `delete_difficulty_level()`
   - Delete `reorder_difficulty_levels()`

2. **Add new profile settings functions**:
   ```python
   def get_difficulty_profile(profile_id: str) -> Dict[str, Any]:
       """Get difficulty profile settings"""
       
   def update_difficulty_profile(profile_id: str, settings: Dict) -> tuple[bool, str]:
       """Update weights, enabled levels, display names"""
   ```

3. **Update validation** (`validate_profile_structure()`):

**Comprehensive validation rules:**

   - **Question types**: Each `question_type` must have a `difficulty_level` field
   - **Global reference**: Each `question_type.difficulty_level` must exist in `GLOBAL_DIFFICULTY_LEVELS`
   - **Profile structure**: Require `difficulty_profile` section if question types exist
   - **Enabled levels**: `difficulty_profile.enabled_levels` must be a subset of global level IDs
   - **Question type coverage**: All enabled levels must have at least one question type
   - **Weights structure**: 
     - `weights` must include every enabled level (or system fills defaults)
     - All weight values must be numeric and non-negative
     - Weights do not need to sum to 1.0 in config (normalized at runtime)
   - **At least one enabled**: `enabled_levels` must contain at least one level ID
   - **Display names**: `display_names` keys should be a subset of enabled levels (optional)

4. **Add migration helper**:
   ```python
   def migrate_profile_to_new_difficulty_system(profile: Dict) -> Dict:
       """Convert old difficulty_levels to new system"""
       # Tag all existing question types as Level 3
       # Create default difficulty_profile
       # Remove old difficulty_levels array
   ```


### Phase 3: Update Blueprint Selection Logic

**File**: [`app/utils/reasoning_controller.py`](app/utils/reasoning_controller.py)

Changes needed:

1. **Modify `select_blueprint()` function** (lines 113-208):

   - Remove separate difficulty level selection
   - Call new two-stage selection function
   - Blueprint returns full question type dict (includes difficulty level)

2. **Replace `select_difficulty_level()` function** with two-stage selection**:

**CRITICAL: Two-Stage Selection Algorithm**

The selection must happen in two stages to ensure weights are predictable:

**Stage 1: Select difficulty level** (using profile weights)

   - Get `enabled_levels` and `weights` from `difficulty_profile`
   - **Normalize weights at runtime** for only the enabled levels
     - Example: If Level 1 disabled, and weights were {1: 0.10, 2: 0.35, 3: 0.55}
     - Normalized: {2: 0.35/(0.35+0.55) = 0.39, 3: 0.55/(0.35+0.55) = 0.61}
   - Get blueprint history for this thread
   - Count recent level usage
   - Apply weighted random selection with LRU bias
   - Return selected level_id

**Stage 2: Select question type within that level**

   - Filter question types to only those with `difficulty_level == selected_level_id`
   - Get recent question type usage from history
   - Use LRU rotation (or equal-weight random) within the filtered types
   - Return full question type dict

**Why two stages?** This prevents one level with many question types from dominating the distribution. Weights control level frequency, not question type frequency.

   ```python
   def normalize_weights(weights: Dict[str, float], enabled_levels: List[str]) -> Dict[str, float]:
       """Normalize weights to sum to 1.0 for only enabled levels"""
       enabled_weights = {k: v for k, v in weights.items() if k in enabled_levels}
       total = sum(enabled_weights.values())
       if total == 0:
           # Equal distribution if all weights are 0
           return {k: 1.0/len(enabled_weights) for k in enabled_weights}
       return {k: v/total for k, v in enabled_weights.items()}
   
   def select_question_type_two_stage(
       thread_id: str,
       profile: Dict,
       enabled_levels: List[str],
       history_depth: int
   ) -> Dict:
       """Two-stage selection: pick level by weights, then type within level"""
       
       # Get difficulty profile settings
       difficulty_profile = profile.get('difficulty_profile', {})
       raw_weights = difficulty_profile.get('weights', {})
       
       # Stage 1: Select difficulty level
       normalized_weights = normalize_weights(raw_weights, enabled_levels)
       
       # Get history and count recent level usage
       history = get_blueprint_history(thread_id, history_depth)
       recent_levels = [bp.get('question_type', {}).get('difficulty_level') 
                        for bp in history if bp.get('question_type')]
       level_counts = Counter(recent_levels)
       
       # Apply LRU bias to weights
       level_weights_with_bias = {}
       for level_id, weight in normalized_weights.items():
           count = level_counts.get(level_id, 0)
           bias = 1.0 / (count + 1)  # Boost underused levels
           level_weights_with_bias[level_id] = weight * bias
       
       # Normalize again after bias
       total_biased = sum(level_weights_with_bias.values())
       final_weights = {k: v/total_biased for k, v in level_weights_with_bias.items()}
       
       # Select level using weighted random
       selected_level = random.choices(
           list(final_weights.keys()),
           weights=list(final_weights.values())
       )[0]
       
       # Stage 2: Select question type within selected level
       question_types = profile.get('question_types', [])
       types_for_level = [qt for qt in question_types 
                          if qt.get('difficulty_level') == selected_level]
       
       if not types_for_level:
           # Fallback: should not happen if validation passed
           types_for_level = question_types
       
       # Get recent question type usage
       recent_type_ids = [bp.get('question_type_id') for bp in history]
       type_counts = Counter(recent_type_ids)
       
       # LRU selection within level
       unused_types = [qt for qt in types_for_level 
                       if qt['id'] not in recent_type_ids]
       
       if unused_types:
           selected_type = random.choice(unused_types)
       else:
           # All types used recently, pick least frequent
           selected_type = min(types_for_level, 
                               key=lambda qt: type_counts.get(qt['id'], 0))
       
       return selected_type
   ```

3. **Update `build_blueprint_constraint()` function** (lines 211-264):

   - Blueprint now contains full question type dict (not just ID)
   - Get difficulty level from `question_type['difficulty_level']`
   - Look up global level description from `difficulty_config.py`
   - Include difficulty guidance in prompt

### Phase 4: Update Prompt Building

**File**: [`app/agents/agent.py`](app/agents/agent.py)

Changes needed in `build_prompt()` function (lines 387-480):

**CRITICAL: Prompt Structure Hierarchy**

The question type phrase + guidance is **PRIMARY**. The difficulty level block is **SUPPORTING** guidance only. Never use language suggesting the difficulty block overrides the question type.

Why? The question type is already difficulty-aligned. The global difficulty block provides additional cognitive context (verbs, description) but should reinforce, not conflict with, the question type's inherent difficulty.

1. **Lines 420-436**: Modify difficulty constraint building:
   ```python
   # Get difficulty level from blueprint's question type
   difficulty_level_id = None
   question_type = blueprint.get('question_type')  # Full dict now, not just ID
   if question_type:
       difficulty_level_id = question_type.get('difficulty_level')
   
   if difficulty_level_id:
       from app.config.difficulty_config import get_level_by_id
       global_level = get_level_by_id(difficulty_level_id)
       
       # Get profile's custom display name if available
       profile_display = profile.get('difficulty_profile', {}).get('display_names', {})
       level_name = profile_display.get(difficulty_level_id, global_level['name'])
       
       # SUPPORTING guidance - reinforces question type, does not override
       difficulty_constraint = f"""
   DIFFICULTY LEVEL GUIDANCE:
   ---
   This question should align with: {level_name}
   Cognitive focus: {global_level['description']}
   Appropriate verbs: {', '.join(global_level['verbs'])}
   
   Note: The question type phrase and guidance above are primary. This difficulty guidance provides additional cognitive context.
   """
   ```


### Phase 5: Update API Endpoints

**File**: [`app/web/server.py`](app/web/server.py)

Changes needed:

1. **Remove old difficulty level endpoints** (lines 1113-1165):

   - Delete `/api/exam_profiles/<profile_id>/difficulty_levels` GET
   - Delete `/api/exam_profiles/<profile_id>/difficulty_levels` POST
   - Delete `/api/exam_profiles/<profile_id>/difficulty_levels/<level_id>` PUT
   - Delete `/api/exam_profiles/<profile_id>/difficulty_levels/<level_id>` DELETE

2. **Add new endpoints**:
   ```python
   @app.route("/api/exam_profiles/<profile_id>/difficulty_settings", methods=["GET"])
   def get_difficulty_settings(profile_id):
       """Get current difficulty profile settings"""
   
   @app.route("/api/exam_profiles/<profile_id>/difficulty_settings", methods=["PUT"])
   def update_difficulty_settings(profile_id):
       """Update weights, enabled levels, display names"""
   
   @app.route("/api/global_difficulty_levels", methods=["GET"])
   def get_global_difficulty_levels():
       """Get canonical difficulty level definitions"""
   ```

3. **Update `/api/chat/<agent_id>` endpoint** (lines 1400-1454):

   - Already reads `enabled_levels` from request ✓
   - Already stores in `g.enabled_difficulty_levels` ✓
   - **Enhance response to include comprehensive difficulty metadata**:
   ```python
   # After generating response, extract difficulty info from blueprint
   difficulty_metadata = None
   try:
       blueprint = getattr(g, 'current_blueprint', None)
       if blueprint and 'question_type' in blueprint:
           question_type = blueprint['question_type']
           difficulty_level_id = question_type.get('difficulty_level')
           
           if difficulty_level_id:
               from app.config.difficulty_config import get_level_by_id
               global_level = get_level_by_id(difficulty_level_id)
               
               # Get profile's custom display name
               profile = get_profile(agent.exam_profile_id)
               display_names = profile.get('difficulty_profile', {}).get('display_names', {})
               
               difficulty_metadata = {
                   'question_type_id': question_type['id'],
                   'question_type_phrase': question_type['phrase'],
                   'difficulty_level_id': difficulty_level_id,
                   'difficulty_level_display_name': display_names.get(difficulty_level_id, global_level['name']),
                   'difficulty_level_global_name': global_level['name']
               }
   except (RuntimeError, AttributeError):
       pass
   
   return jsonify({
       "success": True,
       "response": response,
       "agent_name": agent.name,
       "session_id": session_id,
       "difficulty": difficulty_metadata  # Full metadata for UI/analytics
   })
   ```


This ensures the frontend has all information needed for display and analytics.

### Phase 6: Update Frontend - Profile Editor

**File**: [`app/web/templates/exam_profiles.html`](app/web/templates/exam_profiles.html)

Major UI restructuring needed:

1. **Remove "Difficulty Levels" tab** (the one that managed CRUD for levels)

2. **Update "Question Types" tab**:

   - Add difficulty level dropdown to each question type row
   - Show badge indicating level (e.g., `[Level 1]`, `[Level 2]`, `[Level 3]`)
   - Validate that each question type has a difficulty level assigned

3. **Add "Difficulty Settings" section** (in profile editor modal):

**Important**: Don't hardcode level IDs. Fetch from `/api/global_difficulty_levels` and generate UI dynamically.

   ```html
   <div class="difficulty-settings">
       <h4>Difficulty Distribution</h4>
       
       <!-- Enabled Levels (dynamically generated) -->
       <div id="enabled-levels-container">
           <!-- JavaScript populates this based on global levels -->
       </div>
       
       <!-- Weights (dynamically generated with auto-normalization) -->
       <div id="weights-container">
           <!-- JavaScript generates sliders for each global level -->
           <!-- Sum validation: must total 100% -->
           <!-- Auto-redistribute when slider changes -->
       </div>
       
       <!-- Custom Display Names (dynamically generated) -->
       <div id="display-names-container">
           <!-- JavaScript generates inputs with global names as placeholders -->
       </div>
       
       <div class="text-xs text-gray-500 mt-2">
           Weights are normalized at runtime based on enabled levels.
           If you disable a level, its weight is redistributed proportionally.
       </div>
   </div>
   ```

**JavaScript behavior**:

   - Fetch global levels on page load
   - Generate checkboxes, sliders, and name inputs dynamically
   - Validate slider sum = 100% (with auto-adjust helper)
   - Show warning if enabled level has no question types

4. **JavaScript changes**:

   - Remove `loadDifficultyLevels()`, `addDifficultyLevel()`, `removeDifficultyLevel()` functions
   - Add `loadDifficultySettings()`, `saveDifficultySettings()` functions
   - Add weight slider validation with auto-adjustment:
     - As user drags one slider, auto-adjust others to maintain 100% sum
     - Show live percentage display next to each slider
     - Disabled levels' weights are grayed out (not included in sum)
     - "Reset to Equal" button distributes weight evenly among enabled levels
   - Validate before save: at least one level enabled, weights sum to 100%

### Phase 7: Update Frontend - Test Interface

**File**: [`app/web/templates/test.html`](app/web/templates/test.html)

Minor changes needed:

1. **Lines 46-50**: Difficulty checkboxes (already exist)

   - Update labels to use profile's display names (fetch from agent's profile)
   - Show count of available question types per level

2. **Add info display**:
   ```html
   <div id="level-info" class="text-xs text-gray-500">
       Level 1: 2 question types available
       Level 2: 3 question types available
       Level 3: 5 question types available
   </div>
   ```

3. **JavaScript `onAgentChange()` function**:

   - Fetch agent's profile difficulty settings
   - Populate checkboxes with custom display names
   - Show question type counts per level

### Phase 8: Update Example Profile

**File**: [`exam_profile_example.json`](exam_profile_example.json)

Replace the current structure:

1. **Remove `difficulty_levels` array** (lines 171-213)

2. **Update `question_types` array** - add `difficulty_level` field to each:
   ```json
   "question_types": [
     {
       "id": "definition",
       "difficulty_level": "1",
       "phrase": "What is the definition of",
       "guidance": "Test direct recall. Stem should be short..."
     },
     {
       "id": "identification", 
       "difficulty_level": "1",
       "phrase": "Which of the following is an example of",
       "guidance": "Test recognition..."
     },
     {
       "id": "scenario_apply",
       "difficulty_level": "2",
       "phrase": "In this scenario, which principle applies",
       "guidance": "Test application to realistic scenario..."
     },
     {
       "id": "comparative",
       "difficulty_level": "3",
       "phrase": "Which is BEST/MOST appropriate?",
       "guidance": "Frame answers as competing options..."
     }
     // ... existing Level 3 types
   ]
   ```

3. **Add `difficulty_profile` section**:
   ```json
   "difficulty_profile": {
     "enabled_levels": ["1", "2", "3"],
     "weights": {
       "1": 0.15,
       "2": 0.35,
       "3": 0.50
     },
     "display_names": {
       "1": "Foundational Knowledge",
       "2": "Scenario Application",
       "3": "Professional Judgment"
     }
   }
   ```

4. **Add documentation comments** explaining the three-layer system

### Phase 9: Migration Script

**File**: `app/utils/migrate_difficulty_refactor.py` (NEW)

Create migration script to update existing profiles:

```python
def migrate_profiles():
    """Migrate all exam profiles to new difficulty system"""
    from app.config.exam_profile_config import get_all_profiles, save_profile
    
    profiles = get_all_profiles()
    
    for profile in profiles:
        # 1. Tag all existing question types as Level 3
        for qt in profile.get('question_types', []):
            if 'difficulty_level' not in qt:
                qt['difficulty_level'] = '3'
        
        # 2. Create default difficulty_profile
        if 'difficulty_profile' not in profile:
            profile['difficulty_profile'] = {
                'enabled_levels': ['1', '2', '3'],
                'weights': {'1': 0.33, '2': 0.33, '3': 0.34},
                'display_names': {
                    '1': 'Level 1',
                    '2': 'Level 2', 
                    '3': 'Level 3'
                }
            }
        
        # 3. Preserve custom display names from old difficulty_levels
        if 'difficulty_levels' in profile:
            for old_level in profile['difficulty_levels']:
                level_id = old_level['level_id']
                if level_id in ['1', '2', '3']:
                    profile['difficulty_profile']['display_names'][level_id] = old_level['name']
            
            # Remove old structure
            del profile['difficulty_levels']
        
        # 4. Save migrated profile
        save_profile(profile)
```

---

## Testing Strategy

### Unit Tests

**Core functionality:**

1. Test global difficulty level lookup with any level ID (not hardcoded to 1,2,3)
2. Test weight normalization when levels are disabled
3. Test two-stage selection: level selection → question type selection
4. Test validation rejects invalid level references
5. Test migration preserves display names

**Critical fixes validation:**

6. Test normalization: disable Level 1, verify weights renormalize correctly
7. Test two-stage distribution: verify level with many types doesn't dominate
8. Test with hypothetical Level 4 to ensure no hardcoded assumptions
9. Test comprehensive validation catches all error conditions
10. Test API response includes all 6 metadata fields

### Integration Tests

**Distribution verification:**

1. Generate 100 questions with weights {1: 0.10, 2: 0.35, 3: 0.55}

   - Verify distribution: ~10 Level 1, ~35 Level 2, ~55 Level 3

2. Generate 100 questions with Level 1 disabled and same weights

   - Verify renormalized distribution: ~39% Level 2, ~61% Level 3

3. Generate questions with only Level 1 enabled → verify all are Level 1 types

**Prompt and response:**

4. Verify prompt includes global difficulty description as supporting guidance
5. Verify prompt does not suggest difficulty overrides question type
6. Verify API returns complete difficulty metadata

**Question quality:**

7. Generate Level 1 questions → verify use definition/identification types
8. Generate Level 3 questions → verify use comparative/evaluation types
9. Verify no cognitive conflict between question type and difficulty block

### Manual Testing

1. Migrate existing CISSP profile
2. Generate 20 questions each with:

   - All levels enabled
   - Only Level 1 enabled
   - Only Level 3 enabled
   - Levels 2 and 3 enabled (verify weight renormalization)

3. Verify UI:

   - Shows correct labels and weights
   - Weight sliders auto-adjust to maintain 100%
   - Disabled levels don't contribute to weight sum

4. Test profile editor: create profile with only Level 2 and 3 question types, verify validation

---

## Rollback Plan

If issues arise during or after deployment:

1. **Feature flag**: Add `USE_NEW_DIFFICULTY_SYSTEM` config flag

   - Set to `False` to revert to old system behavior
   - Both code paths coexist for one version cycle
   - Allows A/B testing and gradual rollout

2. **API versioning**: 

   - New endpoints: `/api/exam_profiles/<id>/difficulty_settings`
   - Old endpoints: `/api/exam_profiles/<id>/difficulty_levels` (deprecated but functional)
   - Mark old endpoints with `X-Deprecated: true` header
   - Remove old endpoints after one major version

3. **Data migration reversibility**:

   - Keep backup of `exam_profiles.json` before migration
   - Migration script creates `exam_profiles.json.backup_<timestamp>`
   - Rollback script available to restore old structure from backup

4. **Gradual deprecation timeline**:

   - Version N: Deploy new system, old system still functional
   - Version N+1: Warn when old endpoints used, encourage migration
   - Version N+2: Remove old code entirely

---

## Benefits Summary

1. **Fixes cognitive dissonance**: Question types and difficulty are now aligned
2. **Maintains flexibility**: Exams can still define custom weights and labels
3. **Improves quality**: AI receives clear, non-conflicting instructions
4. **Simplifies configuration**: 3-layer model is clearer than independent dimensions
5. **Enables validation**: System can enforce "all enabled levels have question types"
6. **Better UX**: Users see realistic difficulty distributions (CISSP 10/35/55, CCNA 15/60/25)