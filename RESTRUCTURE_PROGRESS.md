# Workplan Generator v11 Restructure Progress

## Completed Steps ✅

### 1. Branch and Tag (Step 1)
- Created branch: `restructure/v11-core`
- Tagged pre-restructure state: `pre-restructure-v11`

### 2. Built src/core/ Framework-Agnostic Modules (Step 2)
All core business logic extracted from `pipeline.py` into reusable, framework-agnostic modules:

- **`src/core/kb.py`** - Knowledge base loading
  - `load_context_spec()` - Load compiled API spec
  - `load_examples()` - Load six production workplan examples
  - `load_models_schema()` - Load JSON schema for validation
  - `format_examples_for_prompt()` - Format for LLM injection

- **`src/core/llm.py`** - LLM client factory
  - `create_vision_client()` - Doubao vision endpoint (Clarifier)
  - `create_text_client()` - Doubao text endpoint (Generator)

- **`src/core/clarifier.py`** - Clarifier agent logic
  - `clarifier_turn()` - Single turn with [[TASK_READY]] detection
  - `build_initial_history()` - Initialize conversation with image
  - `ClarifierTurn` dataclass - Turn result

- **`src/core/generator.py`** - Generator agent logic
  - `generate_workplan()` - Create workplan JSON from brief
  - `parse_json_with_repair()` - Robust JSON parsing
  - `structural_checks()` - Schema-agnostic validation

- **`src/core/orchestrator.py`** - Pipeline coordination
  - `run_pipeline()` - Callback-driven Clarifier→Generator flow

### 3. Created examples/ Directory (Step 2)
Moved six production workplans from `out/` to `examples/`:
- `siriusred_workplan.json`
- `ki67_workplan.json`
- `SMA_workplan.json`
- `空泡_workplan.json`
- `rnascope_workplan.json`
- `脂滴rgb_workplan.json`

### 4. Refactored pipeline.py (Step 2)
- Now a thin CLI wrapper (~100 lines vs ~400)
- Imports from `src/core/`
- Clean callback pattern for user interaction

### 5. Deleted Dead Layers (Step 3)
Removed:
- `RAG_SYSTEM_README.md`
- `src/knowledge/provider.py` (RAG retrieval)
- `src/agents/` entire directory
- RAG dependencies: chromadb, rank-bm25, jieba, tiktoken
- Added: openai package

## Remaining Steps 📋

### Step 4: Build Reviewer
Create in `src/core/`:

1. **`workplan_schema.py`** - Canonical Workplan Pydantic model
   - Resolve six-example inconsistencies:
     - `reportFields`: objects vs strings
     - `filterConditions.threshold`: `{min,max}` vs string
     - `variant`: singular vs array
     - `pic_split.inputs` shape
   - This becomes the single source of truth for executors

2. **`reviewer.py`** - Two-tier validation
   - **Tier 1 (hard errors)**: Structural invariants (already in `structural_checks()`)
     - Valid jobType set
     - pic_split first, formula last
     - Target/channel reference resolution
   - **Tier 2 (hard errors)**: Schema validation
     - Validate each `create_target` param block against `models_jsonschema.json`
     - Use the composed Segment_ROI/Create_Target schema
   - **Tier 3 (soft warnings)**: Vocabulary checks
     - Method name validity
     - Parameter range suggestions

### Step 5: Orchestration Layer
**Decision needed**: Keep LangGraph or use plain orchestrator?

**Recommendation**: Keep LangGraph (rebuilt over `src/core/`)
- Handles review→generator repair loop
- Handles user-decision restart (accept/restart_agent1/restart_agent2)
- Checkpointing for HTTP pause/resume (MemorySaver/PostgresSaver)

If keeping LangGraph:
- Modernize `src/graph/state.py`:
  - `requirements: dict` → `task_brief: str`
  - `requirements_complete` → `brief_ready: bool`
  - Keep: `clarifier_history`, `current_workplan`, `review_result`, `awaiting_user_input`, `user_decision`
- Modernize `src/graph/workflow.py`:
  - Nodes become 2-4 line wrappers calling `src/core/` functions
  - Graph owns only control flow and routing

If dropping LangGraph:
- Delete `src/graph/`
- API endpoints call `src/core/` directly
- Hand-roll pause/resume and routing logic

### Step 6: Web/API Layer
**Decision needed**: Keep `src/api/main.py` or hand to ZJ_AiDataProxy?

**Current overlap**: Session state in 3 places
1. This repo's `src/api/main.py` (sessions endpoints)
2. LangGraph's checkpointer (thread_id state)
3. ZJ_AiDataProxy (browser↔intranet bridge + session management)

**Recommendation**: Pick one owner for session state

If keeping `src/api/main.py`:
- Modernize to prose contract:
  - Replace `questions[]` with Clarifier's prose message
  - Replace `requirements`-based logic with `brief_ready`/`current_workplan`/`review_result`
  - Surface Reviewer result in user_review step
- LangGraph checkpointer is the single session store
- ZJ_AiDataProxy becomes a thin proxy

If handing to ZJ_AiDataProxy:
- Expose `src/core/orchestrator` as internal API or library
- Retire/demote `src/api/main.py`
- ZJ_AiDataProxy owns all session management

### Step 7: Update Tests
Move battery + leave-one-out harnesses to use `src/core/`:
- `tests/test_clarifier.py` - Import from `src/core.clarifier`
- `tests/test_generator.py` - Import from `src/core.generator`
- Verify parity with validated results

### Step 8: Update Documentation
- `README.md` - New architecture (prose Clarifier, example-driven Generator, compiled-KB)
- `BACKEND_API_GUIDE.md` - Update API contracts (prose messages, brief→workplan flow)
- `CLAUDE.md` - Update project overview with new structure

## Architecture Decisions Needed

### 1. Reviewer→Generator Repair Loop
- **Keep**: Auto-retry with Reviewer feedback (current graph behavior)
- **Change to advisory**: Review is informational only, user decides

### 2. Canonical Workplan Schema
For `workplan_schema.py`, choose one form for each inconsistency:
- `reportFields`: **objects** (more structured) or strings
- `filterConditions.threshold`: **`{min, max}`** (typed) or string
- `variant`: **array** (consistent) or singular string
- `pic_split.inputs`: Validate shape consistency

### 3. LangGraph Decision
- **Keep**: Branchy control flow + resumable HITL is its sweet spot
- **Drop**: Simpler for straightforward linear flow

### 4. Session Owner
- **This repo** (`src/api/main.py` + checkpointer)
- **ZJ_AiDataProxy** (browser-facing bridge owns everything)

## Current Branch State

```
restructure/v11-core
  ├─ 7dda4da - feat: create src/core/ framework-agnostic modules
  └─ 037f943 - refactor: remove RAG stack and old agents
```

## Next Actions

1. Create `src/core/workplan_schema.py` and `src/core/reviewer.py`
2. Wire Reviewer into orchestrator
3. Make architecture decisions (LangGraph, web layer, repair loop)
4. Implement chosen orchestration approach
5. Update tests and documentation
6. Merge to main

## File Structure (Current)

```
workplan-generator/
├── prompts/
│   ├── clarifier_system_prompt.md       ✅ New prose v11
│   └── generator_system_prompt.md       ✅ New v11
├── kb_compiled/                         ✅ Single source of truth
│   ├── kb_ir.json  catalog.{json,md}  context_spec.md  models_jsonschema.json
├── examples/                            ✅ NEW - Six production workplans
│   ├── siriusred_workplan.json  ki67_workplan.json  SMA_workplan.json
│   ├── 空泡_workplan.json  rnascope_workplan.json  脂滴rgb_workplan.json
├── src/
│   ├── core/                            ✅ NEW - Framework-agnostic
│   │   ├── kb.py  llm.py  clarifier.py  generator.py  orchestrator.py
│   ├── knowledge/compiler/              ✅ KEEP - Doc compiler
│   ├── graph/                           ⏳ TO MODERNIZE (if keeping LangGraph)
│   │   ├── state.py  workflow.py
│   └── api/main.py                      ⏳ TO MODERNIZE or hand off
├── tests/                               ⏳ TO UPDATE to use src/core/
├── pipeline.py                          ✅ REFACTORED - Thin CLI wrapper
└── requirements.txt                     ✅ CLEANED - Removed RAG deps
```

## Testing Completed

- ✅ Import test: `from src.core import run_pipeline` works
- ⏳ End-to-end: Requires API credentials, skipped for now
- ⏳ Battery tests: Need update to use src/core/

## Notes

- All core modules are stateless and framework-agnostic
- The six production examples are the Generator's few-shot
- Clarifier uses `[[TASK_READY]]` marker for completion detection
- Generator supports JSON mode with fallback
- Structural validation is schema-agnostic (jobType, ordering, references)
