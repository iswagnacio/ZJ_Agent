# Workplan Generator v11

Multi-agent system for generating microscopy analysis workplans using LangGraph and DouBao LLM.

## Quick Start

```bash
# Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env: ARK_API_KEY, CLARIFIER_MODEL

# Run CLI
python pipeline.py --image test.png --request "统计Ki67阳性率"

# Or run API server
uvicorn src.api.main:app --reload --port 8000
```

Visit http://localhost:8000/docs for API documentation.

## Architecture

### Three-Agent Pipeline

```
Image + Request → Clarifier (prose conversation) → Generator (JSON) → Reviewer → Accept
```

**Clarifier** - Vision LLM analyzes image, converses until `[[TASK_READY]]`
**Generator** - Text LLM creates workplan JSON with few-shot examples
**Reviewer** - Rule-based validation (structural + schema)

### Core Modules (`src/core/`)

Framework-agnostic business logic:
- `clarifier.py`, `generator.py`, `reviewer.py`
- `kb.py` - Load API spec, examples, schema
- `llm.py` - Client factory
- `orchestrator.py` - Callback-driven pipeline

### LangGraph Layer (`src/graph/`)

Thin wrapper for control flow, routing, checkpointing.

### REST API (`src/api/`)

FastAPI endpoints - see auto-generated docs at http://localhost:8000/docs.

## Project Structure

```
workplan-generator/
├── prompts/                          # v11 system prompts
├── kb_compiled/                      # Compiled API docs + schema
├── examples/                         # Six production workplans (few-shot)
├── src/
│   ├── core/                        # Framework-agnostic logic
│   ├── graph/                       # LangGraph workflow
│   ├── api/                         # FastAPI endpoints
│   └── knowledge/compiler/          # Doc compiler
├── tests/                           # Battery tests
├── pipeline.py                      # CLI entry point
└── requirements.txt
```

## Configuration

**Required**:
- `ARK_API_KEY` - DouBao API key
- `CLARIFIER_MODEL` - Vision endpoint (e.g., `ep-xxxx`)

**Optional**:
- `GENERATOR_MODEL` - Text endpoint (defaults to CLARIFIER_MODEL)
- `DATABASE_URL` - PostgreSQL for persistent sessions
- `S3_*` - S3/MinIO for image storage

## Testing

```bash
# Clarifier
python tests/test_clarifier.py image.png "request"

# Generator
python tests/test_generator.py --case SMA --brief briefs/SMA.txt --fewshot siriusred,ki67,rnascope,脂滴rgb
```

See `tests/README_COMPLETE_TESTS.md` for validation results.

## Development

All business logic is in `src/core/` as pure functions. LangGraph and API automatically use updates.

## Production

```bash
gunicorn src.api.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

Use PostgreSQL for sessions, S3 for images.

## Documentation

- API reference: http://localhost:8000/docs (auto-generated Swagger UI)
- `tests/README_COMPLETE_TESTS.md` - Test validation results
