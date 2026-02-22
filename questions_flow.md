# Question Generation Flow Report

## High-Level Summary

The question generation process is a sophisticated pipeline that transforms a user's request into a highly specific exam-style question. It leverages "Exam Profiles" to ensure the generated questions adhere to specific domains, difficulty levels, and question types. The system uses a "Blueprint" mechanism to dynamically select these parameters for each request, ensuring variety and coverage. The flow involves constructing a detailed prompt that includes the blueprint constraints, relevant knowledge base chunks, and conversation history, which is then sent to an AI model (OpenAI or Gemini). The response undergoes a rigorous post-processing phase to filter out unwanted text, validate the format, and check for repetitions before being presented to the user.

## Technical Details

The flow can be broken down into the following key stages:

### 1. Entry Point & Context Setup
*   **File:** `app/web/server.py`
*   The process begins at the `/api/chat/<agent_id>` endpoint.
*   The system retrieves the agent configuration and initializes the Flask request context with the session and enabled difficulty levels.

### 2. Blueprint Generation (The "Brain")
*   **File:** `app/utils/reasoning_controller.py`
*   **Function:** `select_blueprint()`
*   If an Exam Profile is active, a "Blueprint" is generated. This is a crucial step that determines *what* kind of question will be asked.
*   **Logic:**
    *   **Domain Selection:** Checks for domain hints in the user's message; otherwise, rotates through domains using an LRU (Least Recently Used) strategy.
    *   **Question Type Selection:** Uses a two-stage process involving difficulty levels (weighted selection) and specific question types within those levels.
    *   **Reasoning Mode:** Rotates through different reasoning styles to avoid repetitive question structures.
*   **Output:** A blueprint dictionary stored in `g.current_blueprint`.
*   **Constraint Building:** `build_blueprint_constraint()` converts this blueprint into a natural language instruction to be injected into the prompt.

### 3. Knowledge Retrieval
*   **File:** `app/agents/agent.py`
*   **Function:** `search_agent_knowledge_bases()` -> `profile_two_stage_retrieval()`
*   The system employs a specialized two-stage retrieval strategy for exam profiles:
    *   **Stage A (Priority):** Fetches 1-2 chunks from a "Priority" or "Outline" Knowledge Base (KB) to ground the question in high-value topics.
    *   **Stage B (Domain):** Fetches 2-4 chunks from a domain-specific KB based on the selected blueprint domain.
*   This ensures the AI has the specific facts needed to construct a valid question for the chosen topic.

### 4. Prompt Construction
*   **File:** `app/agents/agent.py`
*   **Function:** `build_prompt()`
*   The prompt is assembled in layers:
    1.  **Identity:** "You are {agent.name}..."
    2.  **Core Instructions:** From the agent's configuration.
    3.  **Difficulty Guidance:** Cognitive context based on the blueprint's difficulty level.
    4.  **Blueprint Constraint:** The specific instruction generated in step 2 (e.g., "Create a Scenario-Based question about Access Control...").
    5.  **Formatting Rules:** Constraints on output format.
    6.  **Knowledge Context:** The retrieved text chunks.
    7.  **History:** Recent conversation context.
    8.  **User Input:** The actual trigger message.

### 5. AI Execution
*   **File:** `app/agents/agent.py`
*   **Functions:** `_generate_with_openai()` or `_generate_with_gemini()`
*   The constructed prompt is sent to the configured provider.
*   For OpenAI, it supports both the newer Responses API (GPT-5.x) and Chat Completions API.

### 6. Response Processing & Validation
*   **File:** `app/utils/response_processor.py`
*   **Function:** `post_process_response()`
*   The raw AI output is cleaned and validated:
    *   **Filtering:** Removes AI meta-talk ("Here is a question...").
    *   **Formatting:** Enforces rules like "questions_only" or "mcq_only".
    *   **Repetition Check:**
        *   **Pattern-based:** Checks for repeated phrases from the previous response.
        *   **Semantic:** Uses embeddings (`generate_signature_embedding()`) to compare the new question's "signature" (stem + answer) against a cache of recent questions to prevent semantic duplicates.
*   If validation fails or repetition is detected, the system triggers a regeneration attempt.

## Recommendations for Improvement

1.  **Structured Output (JSON Mode):**
    *   **Current:** The system relies on text parsing and regex to validate formats (e.g., MCQs).
    *   **Recommendation:** Switch to using the AI providers' native JSON mode or structured output capabilities. This would guarantee the output format (e.g., `{ "stem": "...", "options": [...], "answer": "...", "explanation": "..." }`), reducing parsing errors and the need for complex regex validation.

2.  **Feedback Loop Implementation:**
    *   **Current:** The flow is one-way.
    *   **Recommendation:** Implement a mechanism to capture user feedback (thumbs up/down, "too hard", "irrelevant"). This data could be used to adjust the weights in the `difficulty_profile` or to flag specific KB chunks as unhelpful.

3.  **Enhanced Blueprint Selection:**
    *   **Current:** Uses simple weighted random and LRU.
    *   **Recommendation:** Introduce "Adaptive Selection." If a user consistently gets questions wrong in a specific domain (if that data were tracked), the blueprint selector could prioritize that domain or lower the difficulty level temporarily.

4.  **Pre-computation/Caching of Blueprints:**
    *   **Current:** Blueprints are generated on the fly.
    *   **Recommendation:** For high-traffic scenarios, pre-computing a queue of diverse blueprints per user session could reduce latency and ensure a perfectly balanced mix of questions over a session.

5.  **Critic/Refiner Agent:**
    *   **Current:** A single agent generates the question.
    *   **Recommendation:** Introduce a second "Critic" step (or a separate agent call) that reviews the generated question for ambiguity, correctness, and adherence to the blueprint *before* showing it to the user. This "Chain of Thought" or "Reflexion" pattern significantly improves quality.
