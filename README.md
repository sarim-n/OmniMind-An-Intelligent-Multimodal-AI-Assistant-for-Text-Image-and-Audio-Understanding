# Intelligent Multimodal AI Assistant (OmniMind)

A production-grade, local-first multimodal AI assistant combining text, vision, and audio processing. Designed for edge and hybrid deployment with adaptive hardware profiles and zero paid API dependencies.

## Architecture & Monorepo Layout

```
.
├── backend/            # FastAPI application (FastAPI, PyTorch, Transformers, ChromaDB)
│   ├── alembic/        # Database schema migrations
│   ├── app/
│   │   ├── api/        # REST API routing (v1 endpoints: auth, conversations, health)
│   │   ├── core/       # Settings (pydantic-settings), security (JWT/bcrypt), JSON logging
│   │   ├── db/         # SQLAlchemy 2.0 Base, engine, and session management
│   │   ├── models/     # Database entities & metrics table (Mapped[] typed)
│   │   ├── schemas/    # Pydantic request/response schemas
│   │   ├── services/   # Storage, media validation, and ML model wrappers
│   │   ├── workers/    # Background asynchronous task workers
│   │   └── utils/      # General utilities and media processors
│   ├── tests/          # Pytest async test suite
│   ├── pyproject.toml  # Python dependencies & hardware extras (core, gpu, cpu, dev)
│   └── Dockerfile      # Backend container definition
├── frontend/           # Modern React + Vite + TypeScript + Tailwind SPA
│   ├── src/
│   │   ├── components/ # Navigation, status pill, layouts
│   │   ├── pages/      # Login, Chat, Search, Reports, Metrics
│   │   └── api.ts      # API client and health verification
│   └── Dockerfile      # Frontend container definition
├── storage/            # Local data directories (gitignored, kept with .gitkeep)
│   ├── dev.db          # Local SQLite development database
│   ├── uploads/
│   │   ├── images/     # Uploaded image files
│   │   ├── audio/      # Uploaded audio recordings
│   │   └── derived/    # Extracted frames, audio clips, thumbnails
│   └── reports/        # Generated PDF summaries & telemetry exports
├── docs/
│   └── LICENSES.md     # Registry of all models, libraries, and verified open licenses
├── docker-compose.yml  # Multi-container orchestration (Postgres, Backend, Frontend)
├── .env.example        # Comprehensive environment variable documentation
└── Makefile            # Standard development automation targets
```

## Hardware Profiles

Every model is dynamically selected via `PROFILE` in `.env`:

| Profile | Target VRAM | LLM | VLM | ASR | Object Detector |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`cpu`** | System RAM | Qwen2.5-1.5B (int8) | SmolVLM | whisper-base (int8) | RT-DETR small |
| **`gpu_low`** | &le; 8 GB | Qwen2.5-1.5B / 7B 4-bit | Qwen2-VL-2B 4-bit | whisper-small | RT-DETR small |
| **`gpu_mid`** | 12 - 16 GB | Qwen2.5-7B 4-bit | Qwen2-VL-2B/7B 4-bit | whisper-large-v3 | RT-DETR small/medium |
| **`gpu_high`** | &ge; 24 GB | Qwen2.5-14B 4-bit | Qwen2-VL-7B 4-bit | whisper-large-v3 | RT-DETR large |

Set `MOCK_MODELS=true` in `.env` to develop and test against the API and UI without downloading model checkpoints.

## Free-Only & Permissive License Constraint

- Strictly **zero paid APIs** (no OpenAI, Anthropic, ElevenLabs, Google Gemini keys).
- Preferred licenses: **Apache-2.0, MIT, BSD, ISC, OFL**.
- Commercial restrictions or copyleft licenses (e.g. AGPL-3.0 Ultralytics YOLO, non-commercial Qwen2.5-3B) are strictly forbidden. See [`docs/LICENSES.md`](docs/LICENSES.md).

## Quick Start (Automated with Make)

```bash
# 1. Initialize environment configuration
cp .env.example .env

# 2. Install backend and frontend dependencies
make install

# 3. Apply database migrations to local SQLite (storage/dev.db)
make migrate

# 4. Run automated test suite
make test

# 5. Run linter and type checker (ruff, black, mypy)
make lint

# 6. Launch FastAPI backend server (http://127.0.0.1:8000)
make run
```

---

## Run without Docker (Windows PowerShell)

You do **not** need Docker to run or develop locally. The default setup uses SQLite (`storage/dev.db`) and local processes.

### 1. Backend Setup

```powershell
# Copy environment configuration
Copy-Item .env.example .env

# Create Python 3.11 virtual environment
py -3.11 -m venv backend/.venv

# Activate virtual environment
.\backend\.venv\Scripts\Activate.ps1

# Install core and development dependencies
pip install -e "./backend[dev]"

# Run database migrations to initialize SQLite tables
alembic -c backend/alembic.ini upgrade head

# Start FastAPI development server
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --app-dir backend
```

Backend Swagger documentation will be available at: `http://127.0.0.1:8000/docs`

### 2. Frontend Setup

In a separate PowerShell window:

```powershell
cd frontend
npm install
npm run dev
```

Frontend application will be available at: `http://localhost:5173`

### 3. Running Tests and Checks

```powershell
# Run backend tests (isolated in-memory database)
backend/.venv/Scripts/pytest backend/tests

# Run code formatters and linters
backend/.venv/Scripts/ruff check backend/app backend/tests
backend/.venv/Scripts/black --check backend/app backend/tests
backend/.venv/Scripts/mypy backend/app backend/tests
```

---

## Authentication Contract

The API supports both standard OAuth2 password credentials (form data) and direct JSON payloads:

- **Endpoint**: `POST /api/v1/auth/login`
- **OAuth2 Form Data** (`application/x-www-form-urlencoded` or `multipart/form-data`):
  - `username`: User email (e.g., `user@example.com`)
  - `password`: User password
- **JSON Payload** (`application/json`):
  - `{"email": "user@example.com", "password": "password"}`
- **Response**: `{"access_token": "<jwt>", "token_type": "bearer"}`
- Fully compatible with FastAPI's OpenAPI `/docs` Authorize modal.

---

## Unified Multimodal Orchestration (Phase 5)

OmniMind processes text, images, and audio in a single conversational turn via `POST /api/v1/conversations/{id}/messages`.

- **Input Formats**:
  - `multipart/form-data`: `content` (optional text), `language` (optional hint), `images[]` (0..N image files), `audio[]` (0..N audio files).
  - `application/json`: `{"content": "..."}` for legacy text-only messages.
- **Model Memory Manager** (`app/services/model_manager.py`):
  - Maintains model sizes and tracks resident heavy models (`llm`, `vlm`, `asr`, `detector`, `embedder`).
  - Automatically unloads least-recently-used models on `cpu` and `gpu_low` when `MAX_LOADED_MODELS` is reached (`torch.cuda.empty_cache()` + garbage collection).
  - Restricts concurrent heavy model inferences with a semaphore (`MAX_CONCURRENT_INFERENCES`).
- **SSE Stream Events**:
  - `status`: `{stage, message}` (e.g. `ingest`, `audio`, `image`, `vqa`, `generation`)
  - `transcript`: `{attachment_id, language, text, segments_count}`
  - `image_analysis`: `{attachment_id, caption, objects, warnings}`
  - `token`: `{text}` (streamed LLM tokens)
  - `sources`: `{items: [{type, file, timestamp, attachment_id}]}` (inline citations parsed from reply)
  - `done`: `{message_id, metrics: {total_latency_ms, ttft_ms, intent, modalities}}`
  - `error`: `{stage, message}` (graceful degradation if an individual modality fails)
- **Security & Hygiene**: Transcripts, OCR, and visual captions are formatted into delimited passive blocks (`<<<AUDIO ...>>>`, `<<<IMAGE ...>>>`) and treated as untrusted data to prevent prompt injection.

### PowerShell 3-Modality Example (Mock Mode)

To send a 3-modality message (text + image + audio) and read the live SSE event stream:

```powershell
# 1. Register & Login to get JWT Bearer Token
$loginBody = @{
    username = "testuser@example.com"
    password = "SecurePassword123!"
}
$loginRes = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/auth/login" -Method Post -Body $loginBody
$token = $loginRes.access_token
$headers = @{ Authorization = "Bearer $token" }

# 2. Create a Conversation
$conv = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/conversations" -Method Post `
    -Headers $headers -ContentType "application/json" -Body '{"title": "Multimodal Inspection"}'
$convId = $conv.id

# 3. Create sample dummy image and audio files
[IO.File]::WriteAllBytes("sample.png", [Convert]::FromBase64String("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="))
[IO.File]::WriteAllBytes("sample.wav", [Convert]::FromBase64String("UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="))

# 4. Stream 3-modality message using curl.exe
curl.exe -N -X POST "http://127.0.0.1:8000/api/v1/conversations/$convId/messages" `
    -H "Authorization: Bearer $token" `
    -F "content=What is shown in the picture, and does the audio match?" `
    -F "images=@sample.png" `
    -F "audio=@sample.wav"
```

### cURL 3-Modality Example

```bash
curl -N -X POST "http://127.0.0.1:8000/api/v1/conversations/${CONV_ID}/messages" \
  -H "Authorization: Bearer ${JWT_TOKEN}" \
  -F "content=Does the speaker statement align with the chart?" \
  -F "images=@chart.png" \
  -F "audio=@meeting.mp3"
```

---

## Knowledge Vault (Phase 6)

The Knowledge Vault provides cross-modal semantic search across all ingested multimodal assets (audio transcripts, vision analyses, chat conversations, meeting insights) and automated meeting comprehension.

- **Cross-Modal Semantic Search**:
  - Persistent ChromaDB collections in `storage/chroma_vault`: `vault_text` (multilingual text embeddings via `multilingual-e5-small` or `bge-m3`) and `vault_images` (visual embeddings via `google/siglip-base-patch16-224`).
  - **Reciprocal Rank Fusion (RRF)**: Merges text and visual result sets using rank-based weighting ($k=60$) with distance cutoff filters ($L2 \le 1.75$) and cosine similarity scaling.
  - **Optional Cross-Modal LLM Reranking**: When `rerank=true`, candidate passages are re-scored by the local LLM against the user query for maximum precision.
  - **Cross-Lingual Capabilities**: Queries in Hindi, Tamil, or English seamlessly retrieve content across modalities and languages. Non-English queries searching visual representations are automatically translated into English embedding space.
  - **Deep Links & Citations**: Results include structured deep links (`/conversations/{id}?attachment={att_id}&t={start}`) and inline citations (`[audio:filename mm:ss]`, `[image:filename]`).
  - **Strict User Privacy Scoping**: All vector searches, re-indexing, and item deletions are scoped strictly to the authenticated `user_id`.

- **Automatic Meeting Insights & Diarization**:
  - Audio uploads meeting the duration threshold (`MEETING_MIN_DURATION_SEC`, default: 120s) or explicitly requested trigger comprehensive meeting synthesis.
  - Generates:
    - 5-line executive summary
    - Formal agenda and ratified decisions
    - Action items with owner, task description, deadline, and source timestamp
    - Chronological topic timeline (`[{topic, start, end, summary}]`)
    - Interactive chart datasets: talk-time distribution per speaker and topic progression timeline
  - Optional speaker diarization powered by `pyannote.audio` if `HF_TOKEN` is supplied (gracefully degrades to acoustic segment clustering if absent).
  - Automatically indexes meeting action items and decisions into `vault_text` for instant cross-modal search.

### PowerShell Knowledge Vault Examples (Mock Mode)

#### 1. Cross-Modal Text Search (`POST /api/v1/search`)

```powershell
$token = "<your_bearer_token>"
$headers = @{ 
    Authorization = "Bearer $token"
    "Content-Type" = "application/json"
}

# Search across all modalities (text, audio, image)
$searchBody = @{
    query = "Q3 marketing budget"
    modalities = @("text", "audio", "image")
    top_k = 5
    rerank = $false
} | ConvertTo-Json

$results = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/search" -Method Post -Headers $headers -Body $searchBody
$results.results | ForEach-Object {
    Write-Host "[$($_.modality.ToUpper())] Score: $($_.score) - $($_.snippet)"
    Write-Host "Deep Link: $($_.deep_link)"
}
```

#### 2. Reverse Image Search (`POST /api/v1/search/by-image`)

```powershell
# Search the vault using an uploaded query image
curl.exe -X POST "http://127.0.0.1:8000/api/v1/search/by-image" `
    -H "Authorization: Bearer $token" `
    -F "image=@sample.png" `
    -F "top_k=5"
```

#### 3. Automatic Meeting Insights (`GET /api/v1/audio/{attachment_id}/meeting`)

```powershell
# Retrieve meeting executive summary, agenda, action items, and topic timeline
$meeting = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/audio/$attachmentId/meeting" `
    -Method Get -Headers $headers

Write-Host "Summary: `n$($meeting.executive_summary)"
Write-Host "`nAction Items:"
$meeting.action_items | ForEach-Object {
    Write-Host "- [$($_.source_timestamp)s] $($_.owner): $($_.task) (Due: $($_.deadline))"
}
```

---

## Structured Reports & PDF Export (Phase 7)

OmniMind can synthesize an entire multimodal conversation (dialogue history, audio transcripts, meeting insights, image analyses, and telemetry) into an auditable, multi-page PDF intelligence report.

- **Factual Integrity & Non-Hallucination**:
  - Tables for detected objects, action items, meeting timelines, and telemetry are populated directly from persistent database records.
  - The local LLM generates only narrative elements (executive summary, thematic sections, cross-modal observations, conclusions, and recommendations).
- **ReportLab Platypus Engine**:
  - Built with ReportLab Platypus (BSD-3-Clause) — strictly zero GPL/AGPL dependencies.
  - Multi-page documents featuring cover pages, structured tables of contents, running headers and footers with two-pass page numbering ("Page X of Y"), and styled tables with repeated headers across page splits.
- **Multilingual Script Support**:
  - Automatically selects typography per paragraph based on script detection (`\u0900-\u097F` for Devanagari, `\u0B80-\u0BFF` for Tamil, Latin for English).
  - Uses Google Noto Sans (OFL-1.1), downloadable via `make download-fonts`.
- **Security & Prompt Hygiene**:
  - All transcripts, OCR text, and user inputs are handled as untrusted passive evidence enclosed in delimited blocks.
  - Stray XML/HTML characters (`<`, `>`, `&`) are escaped to prevent PDF compilation crashes.

### PowerShell Reports Example (Mock Mode)

```powershell
$token = "<your_bearer_token>"
$headers = @{ 
    Authorization = "Bearer $token"
    "Content-Type" = "application/json"
}

# 1. Enqueue Report Generation Job
$reportReq = @{
    conversation_id = $convId
    options = @{
        length = "standard"        # brief | standard | detailed
        language = "en"            # or "hi", "ta"
        include_images = $true
        include_metrics = $true
    }
} | ConvertTo-Json

$job = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/reports" `
    -Method Post -Headers $headers -Body $reportReq
$jobId = $job.job_id
Write-Host "Enqueued Report Job: $jobId"

# 2. Poll Job Status
do {
    Start-Sleep -Seconds 1
    $statusRes = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/jobs/$jobId" `
        -Method Get -Headers $headers
    Write-Host "Job Status: $($statusRes.status) ($([int]($statusRes.progress * 100))%)"
} while ($statusRes.status -in @("queued", "running"))

$reportId = $statusRes.result.report_id
Write-Host "Report Generated Successfully: $reportId"

# 3. Download Compiled PDF
$pdfOutPath = "OmniMind_Report.pdf"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/reports/$reportId/pdf" `
    -Method Get -Headers $headers -OutFile $pdfOutPath
Write-Host "Downloaded PDF Report to: $pdfOutPath"
```

---

## Running with Real Models

By default, `MOCK_MODELS=true` is enabled for fast offline tests and CI. To run real Hugging Face open-source models:

1. **Configure `.env`**:
   ```dotenv
   MOCK_MODELS=false
   PROFILE=cpu          # or gpu_low (<=8GB VRAM) / gpu_mid / gpu_high
   MAX_LOADED_MODELS=2  # memory manager LRU eviction threshold
   ```

2. **Pre-download Model Checkpoints**:
   ```powershell
   python backend/scripts/download_models.py
   ```
   This downloads the weights defined in your `PROFILE`:
   - `cpu`: Qwen2.5-1.5B-Instruct (int8), SmolVLM-Instruct, RT-DETR small, faster-whisper base, multilingual-e5-small, SigLIP base
   - `gpu_low`: Qwen2.5-1.5B / 7B 4-bit, Qwen2-VL-2B-Instruct, RT-DETR small, faster-whisper small, BAAI/bge-m3, SigLIP base

3. **Run Knowledge Vault Retrieval Evaluation Benchmark**:
   ```powershell
   backend/.venv/Scripts/python benchmarks/retrieval_eval.py
   ```
   Evaluates Recall@1/5/10 and MRR across multimodal, cross-lingual (English, Hindi, Tamil) queries and writes metrics to `benchmarks/results/`.

4. **Run Real-Model End-to-End Tests**:
   ```powershell
   backend/.venv/Scripts/pytest backend/tests/test_multimodal_orchestration.py -m slow
   ```

5. **Start the Production Backend**:
   ```powershell
   make run
   ```

