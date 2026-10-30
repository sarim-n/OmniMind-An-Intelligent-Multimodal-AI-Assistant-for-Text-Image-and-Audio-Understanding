# Intelligent Multimodal AI Assistant

A production-grade, local-first multimodal AI assistant combining text, vision, and audio processing. Designed for edge and hybrid deployment with adaptive hardware profiles and zero paid API dependencies.

## Architecture & Monorepo Layout

```
.
├── backend/            # FastAPI application (FastAPI, PyTorch, Transformers, ChromaDB)
│   ├── app/
│   │   ├── api/        # REST API routing (v1 endpoints, health)
│   │   ├── core/       # Settings (pydantic-settings), JSON logging (structlog)
│   │   ├── db/         # SQLAlchemy 2.0 models & database sessions
│   │   ├── models/     # Database entities & metrics table
│   │   ├── schemas/    # Pydantic request/response schemas
│   │   ├── services/   # Lazy-loaded singleton ML model service wrappers
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
| **`gpu_mid`** | 12 - 16 GB | Qwen2.5-7B 4-bit | Qwen2-VL-2B/7B 4-bit | whisper-large-v3 | RT-DETR medium |
| **`gpu_high`** | &ge; 24 GB | Qwen2.5-14B 4-bit | Qwen2-VL-7B 4-bit | whisper-large-v3 | RT-DETR large |

Set `MOCK_MODELS=true` in `.env` to develop against the API and UI without downloading model checkpoints.

## Free-Only & Permissive License Constraint

- Strictly **zero paid APIs** (no OpenAI, Anthropic, ElevenLabs, Google Gemini keys).
- Preferred licenses: **Apache-2.0, MIT, BSD, ISC, OFL**.
- Commercial restrictions or copyleft licenses (e.g. AGPL-3.0 Ultralytics YOLO, non-commercial Qwen2.5-3B) are strictly forbidden. See [`docs/LICENSES.md`](docs/LICENSES.md).

## Quick Start

### 1. Environment Configuration

```bash
cp .env.example .env
```

### 2. Automated Setup (Make)

```bash
# Install backend and frontend dependencies
make install

# Run backend automated tests
make test

# Run linter and type checker (ruff, black, mypy)
make lint

# Launch backend API server
make run
```

### 3. Frontend Development Server

```bash
cd frontend
npm run dev
```

The frontend dashboard will be available at `http://localhost:5173`.

### 4. Running with Docker Compose

```bash
# Standard CPU/development stack
docker compose up --build

# With GPU hardware acceleration profile
docker compose --profile gpu up --build
```
