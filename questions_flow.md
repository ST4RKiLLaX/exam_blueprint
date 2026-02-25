# Question Generation Flow Report (Current Implementation)

## High-Level Summary

The flow starts in the Generate Questions UI and ends with a provider response that is post-processed and returned with retrieval/difficulty metadata.

When an agent has an exam profile, the system selects a blueprint (domain/question type/reasoning mode), retrieves profile-aware KB context, builds a constrained prompt, calls the selected provider (OpenAI or Gemini), and post-processes output. Hot-topics behavior is configurable per request/agent/profile and affects retrieval order.

## End-to-End Flow

### 1) UI Request
- **File:** `app/web/templates/generate_questions.html`
- Sends `POST /api/chat/<agent_id>` with:
  - `message`
  - `session_id` (if active)
  - `enabled_levels` (optional selected difficulty level IDs)
  - `hot_topics_mode` (optional: `disabled | assistive | priority`)

### 2) API Entry + Request Context
- **File:** `app/web/server.py`
- **Route:** `chat_with_agent()` at `/api/chat/<agent_id>`
- Validates `hot_topics_mode` values.
- Loads agent and history, then stores context in `flask.g`:
  - `g.thread_id`
  - `g.enabled_difficulty_levels` (if sent)
  - `g.request_hot_topics_mode` (if sent)

### 3) Blueprint Selection (Exam Profile Mode)
- **Files:** `app/agents/agent.py`, `app/utils/reasoning_controller.py`
- In `_generate_with_openai()` / `_generate_with_gemini()`:
  - If `agent.exam_profile_id` exists, calls `select_blueprint(...)`.
  - Stores selected blueprint in `g.current_blueprint`.
  - Builds constraint text via `build_blueprint_constraint(...)` and stores in `g.blueprint_constraint`.

### 4) Retrieval Routing + Hot Topics Modes
- **File:** `app/agents/agent.py`
- **Functions:** `resolve_hot_topics_mode()`, `search_agent_knowledge_bases()`, `profile_two_stage_retrieval()`
- Effective mode precedence:
  1. request override (`g.request_hot_topics_mode`)
  2. agent setting (`agent.hot_topics_mode`)
  3. profile setting (`profile.hot_topics_mode`)
  4. default `priority`

- Retrieval behavior for exam profiles:
  - `disabled` -> Stage B only (`stage_b_only`)
  - `assistive` -> Stage B first, then limited Stage A enrichment (`stage_b_plus_stage_a`)
  - `priority` -> Stage A then Stage B (current classic behavior, with subtopic refinement) (`stage_a_then_stage_b`)

- Metadata captured in request context:
  - `g.hot_topics_mode_effective`
  - `g.hot_topics_used`
  - `g.retrieval_path`

### 5) Prompt Construction
- **File:** `app/agents/agent.py`
- **Function:** `build_prompt()`
- Prompt layers include:
  - Agent identity/instructions
  - Difficulty guidance (derived from blueprint question type difficulty)
  - Formatting rules
  - KB context
  - Current message
  - Truncated conversation history (token budget aware)

### 6) Provider Execution
- **File:** `app/agents/agent.py`
- **Functions:** `_generate_with_openai()`, `_generate_with_gemini()`
- OpenAI path supports Responses API for supported models and Chat Completions fallback where applicable.
- Uses selected provider key name (`agent.provider_key_name`) for key resolution.

### 7) Post-Processing + Return Payload
- **Files:** `app/agents/agent.py`, `app/utils/response_processor.py`, `app/web/server.py`
- Model output is post-processed (unless skipped for structured modes).
- API response includes:
  - `response`
  - `difficulty` metadata (question type + difficulty IDs/names when blueprint is available)
  - `hot_topics_mode_effective`
  - `hot_topics_used`
  - `retrieval_path`

## Accuracy Notes vs Older Versions

- UI template is now `generate_questions.html` (not `test.html`).
- Hot-topics retrieval is no longer fixed priority-only; it is mode-driven with request/agent/profile precedence.
- Chat response now exposes explicit retrieval/hot-topics metadata used by UI diagnostics.
