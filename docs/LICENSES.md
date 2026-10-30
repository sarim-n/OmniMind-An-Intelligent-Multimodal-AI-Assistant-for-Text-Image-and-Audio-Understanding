# Licenses & Third-Party Dependencies

> [!IMPORTANT]
> **License Verification Note**:
> Every machine learning model checkpoint and dataset must have its license verified directly on its respective Hugging Face model card or repository before production deployment. Although all selected weights are under commercial-friendly open-source licenses (Apache-2.0, MIT, BSD), upstream license terms and acceptable use policies may change.

## Compliance & Strict Constraints

This repository adheres strictly to the **Free-Only and Permissive Open-Source constraint**:
- **Allowed Licenses**: Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause, ISC, OFL.
- **Prohibited Licenses**: AGPL, GPL, CC-BY-NC (non-commercial only), and custom research-only restricted licenses.
- **Explicit Exclusions**:
  - `ultralytics` (AGPL-3.0 / Commercial License) — Replaced with `RT-DETR` (Apache-2.0) via Hugging Face Transformers.
  - `Qwen/Qwen2.5-3B` (Restricted research license) — Replaced with `Qwen/Qwen2.5-1.5B-Instruct` and `Qwen/Qwen2.5-7B-Instruct` (both Apache-2.0).
  - Paid proprietary APIs (OpenAI, Anthropic, Google Gemini, ElevenLabs) — Strictly zero paid API dependencies.

---

## Pre-Filled Component & Model License Registry

| Name | Type | License | Source |
| :--- | :--- | :--- | :--- |
| **Qwen/Qwen2.5-1.5B-Instruct** | Model (LLM) | Apache-2.0 | [Hugging Face](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct) |
| **Qwen/Qwen2.5-7B-Instruct** | Model (LLM) | Apache-2.0 | [Hugging Face](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct) |
| **Qwen/Qwen2.5-14B-Instruct** | Model (LLM) | Apache-2.0 | [Hugging Face](https://huggingface.co/Qwen/Qwen2.5-14B-Instruct) |
| **HuggingFaceTB/SmolVLM-Instruct** | Model (VLM) | Apache-2.0 | [Hugging Face](https://huggingface.co/HuggingFaceTB/SmolVLM-Instruct) |
| **Qwen/Qwen2-VL-2B-Instruct** | Model (VLM) | Apache-2.0 | [Hugging Face](https://huggingface.co/Qwen/Qwen2-VL-2B-Instruct) |
| **Qwen/Qwen2-VL-7B-Instruct** | Model (VLM) | Apache-2.0 | [Hugging Face](https://huggingface.co/Qwen/Qwen2-VL-7B-Instruct) |
| **Systran/faster-whisper (whisper-base/small/large-v3)** | Model / Engine (ASR) | MIT | [GitHub](https://github.com/SYSTRAN/faster-whisper) |
| **PekingU/rtdetr_r18vd** | Model (Object Detection) | Apache-2.0 | [Hugging Face](https://huggingface.co/PekingU/rtdetr_r18vd) |
| **PekingU/rtdetr_r50vd** | Model (Object Detection) | Apache-2.0 | [Hugging Face](https://huggingface.co/PekingU/rtdetr_r50vd) |
| **PekingU/rtdetr_r101vd** | Model (Object Detection) | Apache-2.0 | [Hugging Face](https://huggingface.co/PekingU/rtdetr_r101vd) |
| **BAAI/bge-small-en-v1.5** | Model (Text Embedding) | MIT / Apache-2.0 | [Hugging Face](https://huggingface.co/BAAI/bge-small-en-v1.5) |
| **BAAI/bge-base-en-v1.5** | Model (Text Embedding) | MIT / Apache-2.0 | [Hugging Face](https://huggingface.co/BAAI/bge-base-en-v1.5) |
| **BAAI/bge-large-en-v1.5** | Model (Text Embedding) | MIT / Apache-2.0 | [Hugging Face](https://huggingface.co/BAAI/bge-large-en-v1.5) |
| **google/siglip-base-patch16-224** | Model (Image Embedding) | Apache-2.0 | [Hugging Face](https://huggingface.co/google/siglip-base-patch16-224) |
| **google/siglip-so400m-patch14-384** | Model (Image Embedding) | Apache-2.0 | [Hugging Face](https://huggingface.co/google/siglip-so400m-patch14-384) |
| **FastAPI** | Library (Backend) | MIT | [tiangolo/fastapi](https://github.com/tiangolo/fastapi) |
| **Uvicorn** | Library (ASGI Server) | BSD-3-Clause | [encode/uvicorn](https://github.com/encode/uvicorn) |
| **Pydantic / Pydantic Settings** | Library (Validation & Config) | MIT | [pydantic/pydantic](https://github.com/pydantic/pydantic) |
| **SQLAlchemy** | Library (ORM) | MIT | [sqlalchemy/sqlalchemy](https://github.com/sqlalchemy/sqlalchemy) |
| **Alembic** | Library (Database Migrations) | MIT | [sqlalchemy/alembic](https://github.com/sqlalchemy/alembic) |
| **psycopg2-binary** | Library (PostgreSQL Driver) | LGPL-3.0 with Exception / BSD | [psycopg/psycopg2](https://github.com/psycopg/psycopg2) |
| **Structlog** | Library (Structured Logging) | Apache-2.0 / MIT | [hynek/structlog](https://github.com/hynek/structlog) |
| **PyTorch** | Library (ML Framework) | BSD-3-Clause | [pytorch/pytorch](https://github.com/pytorch/pytorch) |
| **Hugging Face Transformers** | Library (Model Inference) | Apache-2.0 | [huggingface/transformers](https://github.com/huggingface/transformers) |
| **Accelerate** | Library (Model Loading & Device Map) | Apache-2.0 | [huggingface/accelerate](https://github.com/huggingface/accelerate) |
| **Sentence-Transformers** | Library (Dense Embeddings) | Apache-2.0 | [UKPLab/sentence-transformers](https://github.com/UKPLab/sentence-transformers) |
| **ChromaDB** | Library (Vector Database) | Apache-2.0 | [chroma-core/chroma](https://github.com/chroma-core/chroma) |
| **OpenCV Python Headless** | Library (Vision Processing) | Apache-2.0 | [opencv/opencv](https://github.com/opencv/opencv) |
| **ReportLab** | Library (PDF Generation) | BSD-3-Clause | [reportlab](https://www.reportlab.com) |
| **JiWER** | Library (ASR Evaluation / WER) | Apache-2.0 | [jitsi/jiwer](https://github.com/jitsi/jiwer) |
| **psutil** | Library (System Resource Monitoring) | BSD-3-Clause | [giampaolo/psutil](https://github.com/giampaolo/psutil) |
| **langdetect** | Library (Language Detection) | Apache-2.0 | [Mimino666/langdetect](https://github.com/Mimino666/langdetect) |
| **python-jose** | Library (JWT Cryptography) | MIT | [mpdavis/python-jose](https://github.com/mpdavis/python-jose) |
| **passlib** | Library (Password Hashing) | BSD-3-Clause | [passlib](https://foss.heptapod.net/python-libs/passlib) |
| **bitsandbytes** | Library (4-bit / 8-bit Quantization) | MIT | [bitsandbytes-foundation/bitsandbytes](https://github.com/bitsandbytes-foundation/bitsandbytes) |
| **pynvml** | Library (NVIDIA Management) | BSD-3-Clause | [gpuopenanalytics/pynvml](https://github.com/gpuopenanalytics/pynvml) |
| **llama-cpp-python** | Library (CPU GGUF Inference) | MIT | [abetlen/llama-cpp-python](https://github.com/abetlen/llama-cpp-python) |
| **Pytest / Pytest-asyncio** | Library (Testing) | MIT | [pytest-dev/pytest](https://github.com/pytest-dev/pytest) |
| **HTTPX** | Library (Async HTTP Client) | BSD-3-Clause | [encode/httpx](https://github.com/encode/httpx) |
| **Ruff** | Tool (Linter / Formatter) | MIT / Apache-2.0 | [astral-sh/ruff](https://github.com/astral-sh/ruff) |
| **Black** | Tool (Code Formatter) | MIT | [psf/black](https://github.com/psf/black) |
| **Mypy** | Tool (Static Type Checker) | MIT | [python/mypy](https://github.com/python/mypy) |
| **React & React-DOM** | Framework (Frontend UI) | MIT | [facebook/react](https://github.com/facebook/react) |
| **Vite** | Tool (Frontend Bundler) | MIT | [vitejs/vite](https://github.com/vitejs/vite) |
| **TypeScript** | Language / Tool | Apache-2.0 | [microsoft/TypeScript](https://github.com/microsoft/TypeScript) |
| **Tailwind CSS** | Library (Styling) | MIT | [tailwindlabs/tailwindcss](https://github.com/tailwindlabs/tailwindcss) |
| **React Router** | Library (Client Routing) | MIT | [remix-run/react-router](https://github.com/remix-run/react-router) |
| **Lucide React** | Library (Icons) | ISC | [lucide-icons/lucide](https://github.com/lucide-icons/lucide) |
