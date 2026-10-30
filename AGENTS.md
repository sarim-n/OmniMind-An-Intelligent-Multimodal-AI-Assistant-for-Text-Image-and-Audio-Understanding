# Project: Intelligent Multimodal AI Assistant

Stack: Python 3.11, PyTorch, FastAPI, Hugging Face Transformers, faster-whisper,
OpenCV, PostgreSQL (SQLAlchemy 2.0 + Alembic), ChromaDB, React (Vite + TypeScript + Tailwind).

## Conventions
- Monorepo: /backend, /frontend, /benchmarks, /docs, docker-compose.yml
- Backend layout: app/{api,core,db,models,schemas,services,workers,utils}
- Every ML model is wrapped in a service class with: load() (lazy, singleton),
  a device-aware config (cuda/cpu, fp16/4-bit), and a unified `.infer()` method
  that returns (result, timing_ms).
- All model names, paths, and thresholds come from app/core/config.py (pydantic-settings, .env).
- Fully typed, docstrings, structured logging (JSON).
- Every endpoint has a pydantic schema and at least one pytest test.
- Never block the event loop with model inference: use run_in_threadpool or a worker.
- Every inference call records latency + memory into a `metrics` table.
- Small, reviewable commits. After each phase, run tests and lint (ruff, black).

## Free-only constraint (hard rule)
- Use ONLY free, open-source models, libraries, datasets, and services. No paid APIs
  or API keys (no OpenAI, Anthropic, Google, ElevenLabs, etc.).
- Preferred licenses: Apache-2.0, MIT, BSD, OFL. Do NOT add AGPL/GPL or research-only
  or non-commercial licensed dependencies (e.g., Ultralytics YOLO, Qwen2.5-3B).
- Gated or token-based resources (e.g., pyannote) must be OPTIONAL with graceful fallback.
- Every model is configured through config.py with a hardware profile:
  PROFILE=cpu | gpu_low (<=8GB) | gpu_mid (12-16GB) | gpu_high
    cpu:      Qwen2.5-1.5B-Instruct (int8/GGUF), whisper-base int8, SmolVLM, RT-DETR small
    gpu_low:  Qwen2.5-1.5B (or 7B 4-bit), Qwen2-VL-2B 4-bit, whisper-small, RT-DETR
    gpu_mid:  Qwen2.5-7B 4-bit, Qwen2-VL-2B/7B 4-bit, whisper-large-v3
- Provide MOCK_MODELS=true to run API/UI without downloading models.
- Maintain /docs/LICENSES.md listing every model, library, dataset, and its license.