"""Application configuration using pydantic-settings."""

from pathlib import Path
from typing import Any, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ProfileType = Literal["cpu", "gpu_low", "gpu_mid", "gpu_high"]

# Model configurations per hardware profile (strictly free, open-source, non-commercial restrictions free)
PROFILE_MODELS: dict[ProfileType, dict[str, str]] = {
    "cpu": {
        "llm": "Qwen/Qwen2.5-1.5B-Instruct",
        "vlm": "HuggingFaceTB/SmolVLM-Instruct",
        "asr": "openai/whisper-base",
        "detector": "PekingU/rtdetr_r18vd",
        "text_embedding": "BAAI/bge-small-en-v1.5",
        "image_embedding": "google/siglip-base-patch16-224",
    },
    "gpu_low": {
        "llm": "Qwen/Qwen2.5-1.5B-Instruct",
        "vlm": "Qwen/Qwen2-VL-2B-Instruct",
        "asr": "openai/whisper-small",
        "detector": "PekingU/rtdetr_r18vd",
        "text_embedding": "BAAI/bge-small-en-v1.5",
        "image_embedding": "google/siglip-base-patch16-224",
    },
    "gpu_mid": {
        "llm": "Qwen/Qwen2.5-7B-Instruct",
        "vlm": "Qwen/Qwen2-VL-7B-Instruct",
        "asr": "openai/whisper-large-v3",
        "detector": "PekingU/rtdetr_r50vd",
        "text_embedding": "BAAI/bge-base-en-v1.5",
        "image_embedding": "google/siglip-base-patch16-224",
    },
    "gpu_high": {
        "llm": "Qwen/Qwen2.5-14B-Instruct",
        "vlm": "Qwen/Qwen2-VL-7B-Instruct",
        "asr": "openai/whisper-large-v3",
        "detector": "PekingU/rtdetr_r101vd",
        "text_embedding": "BAAI/bge-large-en-v1.5",
        "image_embedding": "google/siglip-so400m-patch14-384",
    },
}


class Settings(BaseSettings):
    """Core application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Project metadata
    PROJECT_NAME: str = "Intelligent Multimodal AI Assistant"
    API_V1_PREFIX: str = "/api/v1"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"

    # Hardware profile & mock toggle
    PROFILE: ProfileType = "cpu"
    MOCK_MODELS: bool = False

    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/multimodal_ai"

    # Storage paths
    STORAGE_DIR: Path = Path("storage")

    # Optional model ID overrides (defaults to profile selection)
    LLM_MODEL_ID: str | None = None
    VLM_MODEL_ID: str | None = None
    ASR_MODEL_ID: str | None = None
    DETECTOR_MODEL_ID: str | None = None
    TEXT_EMBEDDING_MODEL_ID: str | None = None
    IMAGE_EMBEDDING_MODEL_ID: str | None = None

    # JWT Authentication
    JWT_SECRET_KEY: str = "dev-secret-key-change-in-production-1234567890"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Upload limits
    MAX_UPLOAD_SIZE_BYTES: int = 50 * 1024 * 1024  # 50 MB
    ALLOWED_IMAGE_EXTENSIONS: list[str] = [".jpg", ".jpeg", ".png", ".webp", ".bmp"]
    ALLOWED_AUDIO_EXTENSIONS: list[str] = [".wav", ".mp3", ".m4a", ".ogg", ".flac"]
    ALLOWED_DOCUMENT_EXTENSIONS: list[str] = [".pdf", ".txt", ".csv"]

    # CORS settings
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                import json

                return json.loads(v)
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        return []

    # Model resolution helpers
    @property
    def effective_llm_model(self) -> str:
        return self.LLM_MODEL_ID or PROFILE_MODELS[self.PROFILE]["llm"]

    @property
    def effective_vlm_model(self) -> str:
        return self.VLM_MODEL_ID or PROFILE_MODELS[self.PROFILE]["vlm"]

    @property
    def effective_asr_model(self) -> str:
        return self.ASR_MODEL_ID or PROFILE_MODELS[self.PROFILE]["asr"]

    @property
    def effective_detector_model(self) -> str:
        return self.DETECTOR_MODEL_ID or PROFILE_MODELS[self.PROFILE]["detector"]

    @property
    def effective_text_embedding_model(self) -> str:
        return self.TEXT_EMBEDDING_MODEL_ID or PROFILE_MODELS[self.PROFILE]["text_embedding"]

    @property
    def effective_image_embedding_model(self) -> str:
        return self.IMAGE_EMBEDDING_MODEL_ID or PROFILE_MODELS[self.PROFILE]["image_embedding"]

    @property
    def active_models(self) -> dict[str, str]:
        return {
            "llm": self.effective_llm_model,
            "vlm": self.effective_vlm_model,
            "asr": self.effective_asr_model,
            "detector": self.effective_detector_model,
            "text_embedding": self.effective_text_embedding_model,
            "image_embedding": self.effective_image_embedding_model,
        }


settings = Settings()
