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

## Running with Docker Compose (PostgreSQL & Multi-Container)

When using Docker, migrations are executed automatically on container startup against PostgreSQL:

```bash
# Standard development stack (Postgres + Backend + Frontend)
docker compose up --build

# With NVIDIA GPU acceleration
docker compose --profile gpu up --build
```
