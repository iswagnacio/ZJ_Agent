# Workplan Generator v11

Multi-agent system for generating microscopy analysis workplans using LangGraph and DouBao LLM.

## Quick Start

```bash
# Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Install boto3 for S3/MinIO support (recommended for large images)
pip install "boto3>=1.34.0"

# Configure
cp .env.example .env
# Edit .env with required settings (see Configuration section)

# Run CLI
python pipeline.py --image test.png --request "统计Ki67阳性率"

# Or run API server
uvicorn src.api.main:app --reload --port 8000
```

Visit http://localhost:8000/docs for API documentation.

## ⚠️ Important: Large Image Handling

The Clarifier agent sends microscopy images to the vision API. For **large images** (e.g., ki67.jpg), inline base64 encoding can exceed API request size limits (400 error).

**Solution**: Configure S3/MinIO object storage to deliver images by reference (presigned URLs) instead of inline base64. This preserves full resolution without modifying pixels.

**Reachability constraint**: The object store must be publicly accessible from the ARK API servers. Localhost MinIO requires a tunnel (see Setup below).

## Architecture

### Three-Agent Pipeline

```
Image + Request → Clarifier (prose conversation) → Generator (JSON) → Reviewer → Accept
```

**Clarifier** - Vision LLM analyzes image, converses until `[[TASK_READY]]`
  - Delivers images via presigned URL (S3/MinIO) or base64 fallback
  - See `clarifier.py:prepare_vision_image_url()` for delivery logic

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

All settings are configured in `.env` file:

### Required Settings

```bash
# LLM API - DouBao (Volcano ARK)
ARK_API_KEY="your-api-key"
ARK_BASE_URL="https://ark.cn-beijing.volces.com/api/v3"
CLARIFIER_MODEL="ep-xxxxxxxxxxxx"  # Vision-capable endpoint
GENERATOR_MODEL="ep-xxxxxxxxxxxx"  # Can be same as CLARIFIER_MODEL
```

### S3/MinIO Storage (Recommended for Large Images)

To avoid 400 errors with large images, configure object storage:

```bash
S3_ENDPOINT="https://your-minio-or-tos-endpoint.com"
S3_BUCKET="workplan-images"
S3_ACCESS_KEY="minioadmin"
S3_SECRET_KEY="minioadmin123"
```

**Options**:
1. **Volcano TOS** (production): Use your TOS endpoint - already reachable from ARK
2. **MinIO with tunnel** (development): See MinIO Setup section below
3. **No S3 configured**: Falls back to inline base64 (works for small images only)

### Optional Settings

```bash
# Test image directory
WORKPLAN_DIR="/path/to/your/workplan/images"

# Application
MAX_CLARIFICATION_ROUNDS=5
MAX_REVIEW_ITERATIONS=3
LOG_LEVEL=INFO

# Database (for persistent sessions)
DATABASE_URL="postgresql://user:pass@localhost/workplan"
```

## MinIO Setup (Development)

For local development with large images, set up MinIO with a public tunnel:

### 1. Install MinIO and Cloudflared

```bash
# macOS
brew install minio/stable/minio cloudflared

# Linux - see https://min.io/download and https://github.com/cloudflare/cloudflared
```

### 2. Start MinIO Server

```bash
mkdir -p minio-data
MINIO_ROOT_USER=minioadmin MINIO_ROOT_PASSWORD=minioadmin123 \
  minio server ./minio-data --address :9000 --console-address :9001 &
```

### 3. Expose via Cloudflared Tunnel

```bash
cloudflared tunnel --url http://localhost:9000 > cloudflared.log 2>&1 &

# Extract the public URL
grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' cloudflared.log | head -1
# Example output: https://mineral-pit-filters-artist.trycloudflare.com
```

### 4. Update .env

```bash
S3_ENDPOINT="https://your-tunnel-url.trycloudflare.com"
S3_BUCKET="workplan-images"
S3_ACCESS_KEY="minioadmin"
S3_SECRET_KEY="minioadmin123"
```

**Note**: Cloudflared free tunnels are temporary. For persistent deployment, use:
- Named Cloudflare tunnels (requires account)
- Volcano TOS (production recommended)
- Public MinIO instance

## Testing

### Unit Tests

```bash
# Clarifier
python tests/test_clarifier.py image.png "request"

# Generator
python tests/test_generator.py --case SMA --brief briefs/SMA.txt --fewshot siriusred,ki67,rnascope,脂滴rgb
```

### End-to-End Pipeline Test

Tests the complete Clarifier → Generator → Reviewer pipeline with 6 test cases:

```bash
# All configuration loaded from .env automatically
python tests/test_pipeline_e2e.py
```

**Requirements**:
- `.env` configured with `ARK_API_KEY`, `CLARIFIER_MODEL`, etc.
- `WORKPLAN_DIR` pointing to test images
- S3/MinIO configured for large images (ki67 case requires this)

**Output**:
- Generated workplans saved to `out_e2e/<case>.json`
- Structured report with brief, workplan skeleton, reviewer status, anchoring check

See `tests/README_COMPLETE_TESTS.md` for validation results.

## Development

All business logic is in `src/core/` as pure functions. LangGraph and API automatically use updates.

## Production Deployment

### Prerequisites

1. **Install boto3** (required for S3/TOS):
   ```bash
   pip install "boto3>=1.34.0"
   ```

2. **Configure .env** with production settings:
   - Use Volcano TOS for `S3_ENDPOINT` (reachable from ARK servers)
   - Set `DATABASE_URL` for PostgreSQL persistent sessions
   - Configure production CORS in `src/api/main.py`

### Run with Gunicorn

```bash
gunicorn src.api.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

### Image Delivery Flow

**Without S3** (fallback):
```
Image file → base64 encode → inline in API request → Vision API
⚠️ Fails for large images (request size > limit)
```

**With S3/MinIO** (recommended):
```
Image file → Upload to S3/TOS → Presigned URL → Vision API fetches from URL
✅ Works for all image sizes, preserves full resolution
```

The system automatically uses S3 when configured, falls back to base64 otherwise. See `src/core/clarifier.py:76-116` and `src/core/orchestrator.py:71`.

## Documentation

- API reference: http://localhost:8000/docs (auto-generated Swagger UI)
- `tests/README_COMPLETE_TESTS.md` - Test validation results
- `CLAUDE.md` - Detailed project guide for Claude Code

## Troubleshooting

### Error: 400 "Timeout while downloading url" or Request Size Limit

**Cause**: Large images (like ki67.jpg) exceed the API request size limit when using inline base64 encoding.

**Solution**: Configure S3/MinIO object storage (see Configuration section above). The system will automatically use presigned URLs instead of base64.

**Verify**: Check logs for message `image_delivery: object-store URL` (not `inline base64`)

### Error: ARK_API_KEY or CLARIFIER_API_KEY must be set

**Cause**: Environment variables not loaded from `.env`

**Solutions**:
1. Ensure `.env` file exists and contains `ARK_API_KEY` and `CLARIFIER_MODEL`
2. For `test_pipeline_e2e.py`, the script automatically loads `.env` (requires `python-dotenv`)
3. For CLI/API, use `python-dotenv` or export manually:
   ```bash
   export $(cat .env | grep -v '^#' | xargs)
   ```

### MinIO Connection Refused / Cloudflared Tunnel Not Accessible

**Cause**: ARK servers cannot reach your localhost MinIO or the tunnel expired

**Solutions**:
1. Verify tunnel is running: `grep trycloudflare cloudflared.log`
2. Test URL externally: `curl https://your-tunnel.trycloudflare.com/minio/health/live`
3. Restart cloudflared if tunnel expired (free tunnels are temporary)
4. For production, use Volcano TOS instead of localhost MinIO

### ImportError: No module named 'boto3'

**Cause**: boto3 not installed (required for S3/MinIO)

**Solution**:
```bash
pip install "boto3>=1.34.0"
```

## Quick Reference

### Essential Commands

```bash
# Setup
pip install -r requirements.txt
pip install "boto3>=1.34.0"
cp .env.example .env  # Then edit with your credentials

# Run tests
python tests/test_pipeline_e2e.py

# Start API server
uvicorn src.api.main:app --reload --port 8000

# MinIO setup (for large images)
minio server ./minio-data --address :9000 --console-address :9001 &
cloudflared tunnel --url http://localhost:9000 &
# Copy tunnel URL to .env as S3_ENDPOINT
```

### Key Files

- `.env` - All configuration (API keys, S3, etc.)
- `src/core/clarifier.py:76-116` - Image delivery logic
- `src/core/orchestrator.py:71-75` - Pipeline entry point
- `tests/test_pipeline_e2e.py` - Full pipeline test

### Environment Variables (`.env`)

**Required**:
- `ARK_API_KEY`, `CLARIFIER_MODEL`, `GENERATOR_MODEL`

**For large images** (recommended):
- `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`

**For tests**:
- `WORKPLAN_DIR` (path to test images)
