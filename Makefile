.PHONY: help install run test lint format migrate download-models

PYTHON ?= python
VENV_DIR ?= backend/.venv

ifeq ($(OS),Windows_NT)
    VENV_BIN = $(VENV_DIR)/Scripts
    EXE = .exe
else
    VENV_BIN = $(VENV_DIR)/bin
    EXE =
endif

VENV_PYTHON = $(VENV_BIN)/python$(EXE)
VENV_PYTEST = $(VENV_BIN)/pytest$(EXE)
VENV_RUFF = $(VENV_BIN)/ruff$(EXE)
VENV_BLACK = $(VENV_BIN)/black$(EXE)
VENV_MYPY = $(VENV_BIN)/mypy$(EXE)
VENV_UVICORN = $(VENV_BIN)/uvicorn$(EXE)
VENV_ALEMBIC = $(VENV_BIN)/alembic$(EXE)

help:
	@echo Intelligent Multimodal AI Assistant - Make Targets:
	@echo   make install         - Install backend and frontend dependencies
	@echo   make run             - Launch FastAPI backend server on port 8000
	@echo   make test            - Run pytest test suite
	@echo   make lint            - Run ruff, black --check, and mypy
	@echo   make format          - Run ruff --fix and black auto-formatters
	@echo   make migrate         - Execute Alembic database migrations
	@echo   make download-models - Pre-download Hugging Face model weights for configured PROFILE

download-models:
	@echo Downloading model weights for configured PROFILE...
	$(VENV_PYTHON) backend/scripts/download_models.py

download-fonts:
	@echo Downloading multilingual Noto Sans fonts into backend/assets/fonts...
	$(VENV_PYTHON) backend/scripts/download_fonts.py

install:
	@echo Installing backend dependencies...
	uv pip install --python $(VENV_PYTHON) -e "./backend[dev]" || pip install -e "./backend[dev]"
	@echo Installing frontend dependencies...
	cd frontend && npm install

run:
	@echo Starting backend server on http://0.0.0.0:8000...
	$(VENV_UVICORN) app.main:app --host 0.0.0.0 --port 8000 --reload --app-dir backend

test:
	@echo Running backend test suite...
	$(VENV_PYTEST) backend/tests -m "not slow"

lint:
	@echo Running ruff check...
	$(VENV_RUFF) check backend/app backend/tests
	@echo Running black check...
	$(VENV_BLACK) --check --config backend/pyproject.toml backend/app backend/tests
	@echo Running mypy type checks...
	$(VENV_MYPY) --config-file backend/pyproject.toml backend/app backend/tests

format:
	@echo Formatting code...
	$(VENV_RUFF) check --fix backend/app backend/tests
	$(VENV_BLACK) --config backend/pyproject.toml backend/app backend/tests

migrate:
	@echo Running database migrations...
	$(VENV_ALEMBIC) -c backend/alembic.ini upgrade head
