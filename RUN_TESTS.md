# How to Run Tests

Quick reference for running different test suites.

## Prerequisites

```bash
cd workplan-generator

# 1. Install dependencies
pip install -r requirements.txt

# 2. Build knowledge index (one-time, or when docs change)
python build_knowledge_index.py
```

## Test Commands

### 1. Test RAG Retrieval System

**Basic retrieval tests** (semantic + keyword queries):
```bash
python tests/rag/test_rag_system.py
```

**Method-specific tests** (cellpose, threshold, weka):
```bash
python tests/rag/test_rag_real_methods.py
```

Expected output:
- ✅ Retrieval results with scores
- ✅ Method-specific filtering
- ✅ Cross-API queries
- ✅ Context formatting

### 2. Test Clarifier with System Prompt

**Verify Clarifier system prompt loading and configuration**:
```bash
conda activate agent  # Activate virtual environment first
python tests/test_clarifier_with_prompt.py
```

Shows:
- 📄 System prompt loaded from `prompts/clarifier_system_prompt.txt`
- ✅ High-level questioning guidance (NOT technical parameters)
- 🎯 Workflow pattern recognition (Ki67, vacuoles, co-localization, etc.)
- 🚫 Technical question avoidance (diameter, flowThreshold, etc.)

Expected output:
- ✅ System prompt loaded successfully
- ✅ All workflow patterns recognized
- ✅ Technical question avoidance verified

### 3. Test Generator with RAG Integration

**Full integration test** (multi-query strategy):
```bash
conda activate agent  # Activate virtual environment first
python tests/test_generator_with_rag.py
```

Shows:
- 🔍 Topic extraction from requirements
- 📝 Multi-query building
- 🔎 Retrieval with observability
- 📄 Context injection

**Note**: API credentials are loaded from `.env` file.

### 4. Test API Endpoints

**Test REST API** (requires API server running):
```bash
# Terminal 1: Start API server
uvicorn src.api.main:app --reload --port 8000

# Terminal 2: Test with client
python test_client.py path/to/image.png "分析需求描述"
```

Or use Swagger UI: http://localhost:8000/docs

## Maintenance

### Rebuild Index When Docs Change

```bash
python build_knowledge_index.py --force-rebuild

# Validate
python build_knowledge_index.py --validate-only
```

### Run All Tests

```bash
conda activate agent  # Activate virtual environment first

# RAG tests
python tests/rag/test_rag_system.py
python tests/rag/test_rag_real_methods.py

# Agent tests
python tests/test_clarifier_with_prompt.py  # Clarifier system prompt
python tests/test_generator_with_rag.py     # Generator RAG integration
```

## Troubleshooting

### "KB index not found"
```bash
# Build the index first
python build_knowledge_index.py
```

### "No results retrieved"
```bash
# Check index exists
ls kb_index/

# Validate index
python build_knowledge_index.py --validate-only
```

### "RAG module not available"
```bash
# Install RAG dependencies
pip install chromadb rank-bm25 jieba tiktoken pyyaml
```
