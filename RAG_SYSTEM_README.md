# Knowledge Integration: RAG System & System Prompts

This system uses two different approaches for providing domain knowledge to agents:

## 🎯 Two-Tier Knowledge Strategy

### Generator Agent → RAG Retrieval
- **Purpose**: Dynamic retrieval of technical API documentation
- **Content**: API parameter specs, schemas, field definitions
- **Method**: Hybrid retrieval (dense + sparse) from `api_docs/`
- **Why RAG**: Allows selective retrieval of only relevant technical specs

### Clarifier Agent → System Prompt
- **Purpose**: Always-available methodology guidance
- **Content**: High-level questioning strategies, workflow patterns, user intent recognition
- **Method**: Embedded in system prompt (`prompts/clarifier_system_prompt.txt`)
- **Why Prompt**: Guidance is prescriptive (how to behave), not reference material

---

## RAG System for Generator Agent

This RAG (Retrieval-Augmented Generation) system provides hybrid retrieval (dense + sparse) for API documentation to enhance the Generator agent's workplan creation capabilities.

## Quick Start

### 1. Install Dependencies

```bash
cd workplan-generator
pip install -r requirements.txt
```

New dependencies added:
- `chromadb>=0.4.22` - Dense vector database
- `rank-bm25>=0.2.2` - Sparse BM25 search
- `jieba>=0.42.1` - Chinese text segmentation
- `tiktoken>=0.5.2` - Token counting
- `pyyaml>=6.0.1` - YAML parsing

### 2. Build Knowledge Index

```bash
python build_knowledge_index.py
```

This will:
- Scan all markdown files in `../api_docs/`
- Chunk documents with structure awareness
- Build dense vector index (Chroma)
- Build sparse BM25 index
- Output to `kb_index/` directory

**Output structure**:
```
kb_index/
├── chunks.jsonl       # Ground truth chunks
├── chroma/            # Dense vector index
├── bm25.pkl          # Sparse BM25 index
└── manifest.json     # Build metadata
```

### 3. Test Retrieval

```bash
python test_rag_system.py
```

This runs comprehensive tests including:
- Exact parameter matching (e.g., `detectpinMin`)
- Method-specific queries (e.g., `cellpose parameters`)
- Semantic queries (e.g., `点检测参数`)
- Mixed Chinese/English queries
- Agent-specific retrieval

## Architecture

### Components

1. **Chunker** (`src/knowledge/rag/chunker.py`)
   - Structure-aware Markdown parsing
   - Preserves method-parameter relationships
   - Adds breadcrumb prefixes for context
   - Protects code blocks and tables

2. **Tokenizer** (`src/knowledge/rag/tokenizer.py`)
   - Custom Chinese/English tokenization
   - Splits camelCase/snake_case identifiers
   - Preserves full identifiers + subwords

3. **Indexer** (`src/knowledge/rag/indexer.py`)
   - Builds both dense and sparse indices
   - Manages persistence and metadata
   - Validation utilities

4. **Retriever** (`src/knowledge/rag/retriever.py`)
   - Hybrid retrieval (dense + sparse)
   - Reciprocal Rank Fusion (RRF)
   - Metadata filtering by doc_type/method_name

## Usage Examples

### Basic Retrieval

```python
from src.knowledge.rag import HybridRetriever

retriever = HybridRetriever(index_path="kb_index")

# Simple query
results = retriever.retrieve(
    query="cellpose diameter parameter",
    top_k=5
)

for result in results:
    print(f"Score: {result.score:.4f}")
    print(f"Heading: {result.heading}")
    print(f"Method: {result.method_name}")
    print(f"Content: {result.content[:200]}...")
    print()
```

### Agent-Specific Retrieval

```python
# Generator agent (needs API specs and schemas)
results = retriever.retrieve_for_agent(
    query="如何使用 cellpose 分割细胞",
    agent_type="generator",
    top_k=5
)

# Clarifier agent (needs methodology and general info)
results = retriever.retrieve_for_agent(
    query="图像分析流程",
    agent_type="clarifier",
    top_k=5
)
```

### Method-Specific Retrieval

```python
# Get documentation for specific method
results = retriever.retrieve_by_method(
    query="parameters threshold settings",
    method_name="cellpose",
    top_k=3
)
```

### Format as LLM Context

```python
results = retriever.retrieve("ROI rendering parameters", top_k=5)

# Format for LLM prompt
context = retriever.format_context(results, max_tokens=4000)

# Use in prompt
prompt = f"""Based on the following API documentation:

{context}

Please create a workplan for...
"""
```

## Integration with Generator Agent

Add retrieval to the Generator agent to enhance workplan creation:

```python
from src.knowledge.rag import HybridRetriever

class GeneratorAgent:
    def __init__(self, ...):
        # ... existing initialization ...

        # Initialize retriever
        self.retriever = HybridRetriever(index_path="kb_index")

    async def generate_workplan(self, requirements: dict, feedback: dict = None):
        # Extract key methods/APIs from requirements
        methods = self._extract_methods(requirements)

        # Retrieve relevant documentation
        context_parts = []
        for method in methods:
            results = self.retriever.retrieve_by_method(
                query=f"{method} parameters",
                method_name=method,
                top_k=3
            )
            context_parts.append(self.retriever.format_context(results))

        api_context = "\n\n".join(context_parts)

        # Include in LLM prompt
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=f"""
Requirements:
{json.dumps(requirements, indent=2)}

Relevant API Documentation:
{api_context}

Please generate the workplan JSON...
""")
        ]

        # ... rest of generation logic ...
```

## Chunking Strategy

The chunker follows these principles:

1. **Structure-Aware**: Chunks by Markdown header levels
2. **Method Preservation**: Keeps methods with parameters together
3. **Breadcrumb Prefixes**: Adds full header path to each chunk
   - Example: `Create_Target > 方法 cellpose > 参数`
4. **Code Block Protection**: Never splits fenced code blocks
5. **Table Protection**: Preserves Markdown tables intact
6. **Smart Merging**: Combines short consecutive chunks

**Chunk metadata**:
- `chunk_id`: Deterministic ID for reproducibility
- `method_name`: Extracted method name (cellpose, rnascope, etc.)
- `doc_type`: api, methodology, schema, deprecated
- `has_code`, `has_table`: Structure indicators
- `token_count`: For context window management

## Tokenization Strategy

For BM25 sparse retrieval:

**Chinese text**:
- Use jieba segmentation
- Example: `细胞分割` → [细胞, 分割]

**English identifiers**:
- Keep full identifier: `detectpinMin`
- Also split camelCase: `detectpin`, `min`
- Also split snake_case: `flow_threshold` → `flow`, `threshold`

**Why this matters**:
- Enables exact matching: query `detectpinMin` finds exact parameter
- Enables partial matching: query `detectpin` also finds `detectpinMin`
- Critical for API documentation where parameter names are precise

## Retrieval Strategy

### Hybrid Approach

**Dense retrieval (Chroma)**:
- Semantic similarity using embeddings
- Handles: "点检测" → "rnascope detection"
- Good for concept matching

**Sparse retrieval (BM25)**:
- Exact keyword matching
- Handles: `detectpinMin`, `flowThreshold`
- Good for precise parameter lookup

**Reciprocal Rank Fusion (RRF)**:
- Combines both methods
- Weights: dense=0.5, sparse=0.5 (configurable)
- Formula: score = Σ(weight / (k + rank))

### Filtering

**By doc_type**:
- `api` - API endpoint documentation
- `methodology` - Analysis methodology guides
- `schema` - JSON schema definitions
- `deprecated` - Legacy documentation

**By method_name**:
- Filter to specific methods: cellpose, threshold, rnascope, etc.
- Useful for Generator to get method-specific parameters

## Maintenance

### Rebuild Index When:

1. API documentation changes
2. Chunking strategy modified
3. New doc_type categories added

```bash
# Force rebuild
python build_knowledge_index.py --force-rebuild

# Validate after rebuild
python build_knowledge_index.py --validate-only
```

### Validation Checks

The validator checks for:
- ✅ Chunk count and token distribution
- ✅ Doc type distribution
- ✅ Method name coverage
- ❌ Empty chunks
- ❌ Oversized chunks (>20% over max)
- ❌ Duplicate chunk IDs

### Tuning Retrieval

Adjust weights based on your use case:

```python
retriever = HybridRetriever(
    index_path="kb_index",
    dense_weight=0.7,   # More semantic
    sparse_weight=0.3   # Less keyword
)
```

When to favor dense:
- General concept queries
- Cross-language queries (Chinese → English)
- Semantic similarity important

When to favor sparse:
- Exact parameter lookups
- Technical identifier matching
- Precise API name queries

## Troubleshooting

### Issue: No results returned

**Check**:
1. Index exists: `ls kb_index/`
2. Index not empty: `python build_knowledge_index.py --validate-only`
3. Query not too specific: try broader query

### Issue: Wrong results at top

**Solutions**:
- Adjust dense/sparse weights
- Check if doc_type filter too restrictive
- Verify method_name extraction in chunks

### Issue: Missing expected method

**Debug**:
```python
# Check what's indexed for a method
retriever = HybridRetriever("kb_index")
results = retriever.retrieve_by_method(
    query="parameters",
    method_name="cellpose",
    top_k=10
)
print(f"Found {len(results)} chunks for cellpose")
```

### Issue: Chunking splits method from parameters

**Fix**:
- Check header structure in source markdown
- Ensure method parameters are under same header section
- Adjust `max_chunk_size` if needed

## Performance

**Indexing**:
- ~11 markdown files: ~5-10 seconds
- Scales linearly with document count

**Retrieval**:
- Single query: ~50-100ms
- Batch queries: parallelize for efficiency

**Memory**:
- Chroma index: ~10-50 MB per 1000 chunks
- BM25 index: ~5-20 MB per 1000 chunks
- Scales with corpus size

## Future Enhancements

Potential improvements:
1. Incremental indexing (only rebuild changed files)
2. Query rewriting for better recall
3. Re-ranking with cross-encoder
4. Multi-modal support (diagrams in docs)
5. Usage analytics for query optimization
