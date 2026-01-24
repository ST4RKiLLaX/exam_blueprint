# ExamBlueprint System Architecture Overview

## System Purpose
ExamBlueprint is a certification exam question generation platform that uses AI agents, structured exam profiles, and knowledge bases to generate high-quality, exam-style questions for professional certifications (CISSP, PMP, etc.).

---

## Core Features

### 1. Exam Profile Feature

**What it is:**
A configuration schema that defines the structure, style, and requirements for a specific certification exam.

**Key Components:**

- **Profile Identity**
  - Unique ID (e.g., `cissp_2026`, `pmp_2024`)
  - Display name and description
  - Used to link agents and knowledge bases to specific exam types

- **Question Types** (5 common patterns)
  - Comparative: "Which is BEST/MOST appropriate?"
  - Sequential: "What should be done FIRST?"
  - Risk Identification: "What is the PRIMARY risk?"
  - Control Selection: "Which control addresses this?"
  - Exception: "When would this NOT apply?"
  - Each type includes guidance on how to construct questions

- **Domains/Subject Areas** (e.g., 8 domains for CISSP)
  - Domain ID and name
  - Keywords for semantic matching
  - Priority levels
  - Used for organizing content and routing queries

- **Reasoning Modes** (4 thinking frameworks)
  - Governance: Policy and compliance lens
  - Risk-Based: Threat → vulnerability → impact → control
  - Process: Lifecycle/phase-based thinking
  - Comparative Analysis: Trade-off evaluation
  - Agents rotate among these to create variety

- **KB Structure Configuration**
  - Defines how knowledge bases are organized
  - Priority KB flag (for outlines/structure documents)
  - Domain type designation (for content documents)
  - Controls the two-stage retrieval system

- **Quality Guidance**
  - Exam-wide instructions sent to agents
  - Constraints and prohibited content
  - Difficulty level expectations
  - Philosophical approach (e.g., "test judgment, not memorization")

**Storage:** `app/config/exam_profiles.json`

**Usage Tracking:** System automatically tracks which agents and KBs reference each profile

---

### 2. Agent Feature

**What it is:**
An AI-powered question generation engine configured with specific personality, instructions, and generation parameters. Each agent is a complete "question writer" with its own style and approach.

**Key Components:**

- **Identity & Behavior**
  - Unique ID (UUID)
  - Display name (typically includes provider: "Agent Name (GPT)")
  - Status: active or inactive
  - Linked to one exam profile

- **Instruction Set** (4 separate fields for clarity)
  - **Personality**: Who you are (role, values, priorities)
  - **Style**: How you communicate (tone, formality, language)
  - **Prompt**: What you do (question structure, content requirements, diversity rules)
  - **Formatting**: How to present output (exact format, explanation style)

- **Provider Configuration**
  - LLM provider (OpenAI, Gemini, Anthropic)
  - Specific model (gpt-4o, gemini-2.0-flash-exp, etc.)
  - Temperature, penalties, token limits
  - Reasoning effort (for o-series models)

- **Knowledge Access**
  - Array of knowledge base IDs
  - Retrieval settings (chunk count, similarity threshold)
  - Conversation history token limit

- **Quality Control**
  - Semantic duplicate detection (enabled/disabled)
  - Similarity threshold for blocking duplicates
  - History depth (how many recent questions to check)
  - Post-processing rules (word limits, framework stripping, etc.)

- **Domain Balancing**
  - Blueprint history depth
  - Tracks recent domain selections
  - Can prefer under-represented domains

**Storage:** `app/config/agents.json`

**UI Management:** Create, edit, activate/deactivate, export/import agents

---

### 3. Knowledge Base Feature

**What it is:**
Document repositories that provide source material for question generation. Each KB contains processed, embedded content that agents can query semantically.

**Key Components:**

- **Content Storage**
  - Original source file (PDF, DOCX, TXT, or URL)
  - Processed chunks (text segments)
  - Embeddings (vector representations)
  - FAISS index (for fast semantic search)

- **Metadata**
  - Title and description
  - KB type (outline, cbk/domain content, reference, etc.)
  - Category (general, technical, governance, etc.)
  - Access type (shared or exclusive)

- **Profile Assignment**
  - Can be assigned to multiple exam profiles
  - Each assignment can have:
    - Profile type (outline vs cbk)
    - Domain designation (which domain it covers)
    - Priority flag (is_priority_kb: true/false)

- **Embedding Configuration**
  - Provider (OpenAI, Gemini)
  - Model used for embeddings
  - Status (pending, processing, completed, failed)

- **Refresh Settings**
  - Schedule (manual, daily, weekly)
  - Last refreshed timestamp
  - Next refresh time

**Storage Structure:**
```
app/knowledge_bases/
  ├── source_file.pdf              (original)
  └── kb_{id}/
      ├── chunks.pkl.gz            (processed text chunks)
      ├── embeddings.npy           (vector embeddings)
      └── index.faiss              (search index)
```

**Metadata Storage:** `app/config/knowledge_bases.json`

**Processing Pipeline:**
1. Upload file or provide URL
2. Extract text content
3. Chunk into manageable segments (800 tokens with 200 token overlap)
4. Generate embeddings using selected provider
5. Build FAISS index for fast similarity search
6. Mark as completed and ready for use

**Import/Export:**
- Export KB as ZIP package (includes source, embeddings, metadata)
- Import KB from package
- Smart embedding reuse (instant if provider matches, re-process if different)

---

## Question Generation Flow

### High-Level Process

```
User Request → Agent Selection → Profile Loading → KB Retrieval → 
Prompt Construction → LLM Call → Response Parsing → Duplicate Check → 
Quality Validation → Return Question
```

### Detailed Flow

**Step 1: User Initiates Generation**
- Selects active agent from dropdown
- Optionally specifies:
  - Domain/subject area
  - Question type
  - Custom topic/prompt
  - Number of questions

**Step 2: System Setup**
- Load selected agent configuration
- Load linked exam profile
- Identify available knowledge bases (KBs assigned to both agent AND profile)
- Initialize generation context

**Step 3: Two-Stage Knowledge Retrieval**

This is a key architectural feature:

**Stage 1: Priority KB Query (Structure/Outline)**
- Query KBs marked with `is_priority_kb=true`
- These contain exam outlines, domain structures, topic lists
- Purpose: Establish context and topic boundaries
- Returns: High-level structure and relevant topics

**Stage 2: Domain-Specific KB Query (Content)**
- If domain specified, query KBs assigned to that domain
- If no domain specified, query based on semantic match to user prompt
- These contain detailed subject matter
- Purpose: Get specific technical content and examples
- Returns: Detailed content chunks relevant to the topic

**Retrieval Parameters:**
- Uses agent's `max_knowledge_chunks` setting
- Filters by `min_similarity_threshold`
- Ranks by cosine similarity

**Step 4: Prompt Construction**

The system builds a comprehensive prompt by combining:

1. **Agent Instructions**
   - Personality
   - Style
   - Prompt (core instructions)
   - Formatting requirements

2. **Exam Profile Context**
   - Selected question type (with guidance)
   - Selected domain (with keywords)
   - Selected reasoning mode (with description)
   - Guidance suffix

3. **Retrieved Knowledge**
   - Relevant chunks from priority KBs
   - Relevant chunks from domain KBs
   - Formatted as context

4. **User Input**
   - Custom topic/prompt (if provided)
   - Domain preference (if specified)
   - Any special instructions

5. **History Context**
   - Recent questions (for diversity)
   - Limited by `conversation_history_tokens`

**Step 5: LLM Generation**
- Send constructed prompt to provider (OpenAI/Gemini/Anthropic)
- Use agent's configured parameters (temperature, penalties, etc.)
- Receive structured response
- Handle timeouts and errors

**Step 6: Response Processing**

**Parsing:**
- Extract question stem
- Extract options A, B, C, D
- Extract correct answer letter
- Extract explanation

**Post-Processing (if configured):**
- Enforce word/sentence limits
- Strip framework names
- Validate format structure

**Step 7: Quality Checks**

**Semantic Duplicate Detection:**
- If enabled, generate embedding of new question
- Compare to last N questions (semantic_history_depth)
- Calculate cosine similarity
- If similarity >= semantic_similarity_threshold, reject and retry
- Prevents generating nearly identical questions in a session

**Format Validation:**
- Ensure all required components present
- Verify correct answer is one of A, B, C, D
- Check explanation exists

**Step 8: Domain Tracking**
- Record which domain was used
- Update blueprint history
- Used for future balancing decisions

**Step 9: Return to User**
- Display formatted question
- Store in session history
- Enable actions (regenerate, save, export)

---

## Data Flow Diagram (Conceptual)

```
┌─────────────────┐
│  User Interface │
└────────┬────────┘
         │ Selects Agent + Domain/Topic
         ↓
┌─────────────────┐
│  Agent Config   │ ← Links to → ┌──────────────────┐
│  - Instructions │              │  Exam Profile    │
│  - Parameters   │              │  - Question Types│
│  - KB List      │              │  - Domains       │
└────────┬────────┘              │  - Reasoning     │
         │                       │  - Guidance      │
         │                       └──────────────────┘
         ↓
┌─────────────────┐
│  KB Retrieval   │
│  System         │
└────────┬────────┘
         │
         ├─→ Stage 1: Priority KBs (outline/structure)
         │   └─→ Returns: Topic context
         │
         └─→ Stage 2: Domain KBs (content)
             └─→ Returns: Detailed chunks
         
         ↓ (combine)
         
┌─────────────────┐
│  Prompt Builder │
│  Combines:      │
│  - Agent prompt │
│  - Profile data │
│  - KB chunks    │
│  - User input   │
└────────┬────────┘
         ↓
┌─────────────────┐
│  LLM Provider   │ (OpenAI/Gemini/Anthropic)
└────────┬────────┘
         ↓
┌─────────────────┐
│  Parser &       │
│  Validator      │
└────────┬────────┘
         │
         ├─→ Duplicate Check
         ├─→ Format Validation
         └─→ Post-Processing
         
         ↓
┌─────────────────┐
│  Return Question│
│  to User        │
└─────────────────┘
```

---

## Key System Behaviors

### Profile-Driven Generation
- Exam profile defines the "rules of the game"
- Agent operates within those rules
- Different profiles = different question styles/approaches
- Easy to add new certification types

### Two-Stage Retrieval Intelligence
- Priority KBs provide structure/outline/organization
- Domain KBs provide detailed content
- Prevents mixing irrelevant content
- Improves accuracy of domain-specific questions

### Semantic Duplicate Prevention
- Uses embedding similarity (not exact text matching)
- Catches paraphrased duplicates
- Configurable sensitivity
- Balances variety vs blocking legitimate variations

### Domain Balancing
- Tracks recent domain selections
- Can prefer under-represented domains
- Ensures comprehensive coverage across exam topics
- Prevents clustering in one area

### Multi-Profile KB Assignment
- Single KB can serve multiple profiles
- Reuse content for related certifications
- Reduces storage and processing needs
- Example: Security fundamentals KB used for CISSP, Security+, etc.

### Provider Flexibility
- Agents can use different LLM providers
- Compare quality across providers
- Use best provider for specific question types
- Fallback options if one provider unavailable

---

## Import/Export System

### Exam Profiles
- Export as JSON
- Import to different installation
- Enables sharing profile configurations
- Preserves all settings and guidance

### Agents
- Export as JSON with KB metadata
- Import generates new agent ID
- Clears KB assignments (user must reassign)
- Validates profile exists on import

### Knowledge Bases
- Export as ZIP package containing:
  - manifest.json (metadata + compatibility info)
  - source/ (original file)
  - processed/ (optional embeddings)
- Import logic:
  - If embedding provider matches: instant (reuse embeddings)
  - If different provider: re-process (2-5 minutes)
  - Validates profile references
  - Generates new KB ID

This enables sharing "starter packs" of profiles, agents, and KBs for specific certifications.

---

## Summary

**ExamBlueprint Architecture = Profiles + Agents + Knowledge Bases**

- **Exam Profiles**: Define the rules and structure
- **Agents**: Execute the generation with specific styles
- **Knowledge Bases**: Provide the source material
- **Two-Stage Retrieval**: Intelligently queries structure then content
- **Quality Controls**: Prevent duplicates and enforce standards
- **Portability**: Export/import enables sharing and backup

The system is designed to be **extensible** (add new exams), **flexible** (multiple agents per exam), **intelligent** (semantic retrieval and duplicate detection), and **shareable** (import/export functionality).
