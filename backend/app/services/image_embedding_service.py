"""SigLIP-based Multimodal Image Embedding Service for Cross-Modal Search."""

from __future__ import annotations

import hashlib
import io
import math
import time
from pathlib import Path
from typing import Any

from PIL import Image

from app.core.config import settings
from app.core.logging import get_logger
from app.services.metrics_service import track

logger = get_logger(__name__)

SIGLIP_DIM = 768


def _hash_to_vector(text_or_bytes: str | bytes, dim: int = SIGLIP_DIM) -> list[float]:
    """Deterministically derive a dim-sized float vector from string or bytes."""
    if isinstance(text_or_bytes, str):
        seed_bytes = hashlib.sha256(text_or_bytes.strip().lower().encode("utf-8")).digest()
    else:
        seed_bytes = hashlib.sha256(text_or_bytes).digest()

    raw_vals: list[float] = []
    current_hash = seed_bytes
    while len(raw_vals) < dim:
        for i in range(0, len(current_hash) - 1, 2):
            val = ((current_hash[i] << 8) | current_hash[i + 1]) / 65535.0 - 0.5
            raw_vals.append(val)
            if len(raw_vals) >= dim:
                break
        current_hash = hashlib.sha256(current_hash).digest()

    return raw_vals


def _semantic_mock_vector(tokens: list[str], dim: int = SIGLIP_DIM) -> list[float]:
    """Compute an L2-normalized deterministic vector by summing token vector hashes."""
    if not tokens:
        tokens = ["default"]

    combined = [0.0] * dim
    for token in tokens:
        token_vec = _hash_to_vector(token, dim=dim)
        for i in range(dim):
            combined[i] += token_vec[i]

    norm = math.sqrt(sum(v * v for v in combined)) or 1.0
    return [round(v / norm, 6) for v in combined]


class MockImageEmbedder:
    """Deterministic mock for SigLIP cross-modal image and text embeddings."""

    def __init__(self, dim: int = SIGLIP_DIM) -> None:
        self.dim = dim

    def embed_images(self, images: list[Any]) -> list[list[float]]:
        """Embed images into 768-d unit vectors deterministically."""
        results: list[list[float]] = []
        for img in images:
            tokens: list[str] = []
            if isinstance(img, (str, Path)):
                p = Path(img)
                name_tokens = p.stem.replace("_", " ").replace("-", " ").split()
                tokens.extend(name_tokens)
            elif isinstance(img, Image.Image):
                # Sample image properties and bytes snippet
                w, h = img.size
                tokens.append(f"{w}x{h}")
                tokens.append(img.mode)
                # Sample pixel center
                try:
                    px = img.getpixel((w // 2, h // 2))
                    tokens.append(str(px))
                except Exception:
                    pass
            elif isinstance(img, bytes):
                # Hash first 512 bytes
                tokens.append(hashlib.md5(img[:512]).hexdigest()[:8])
            else:
                tokens.append(str(type(img)))

            results.append(_semantic_mock_vector(tokens, dim=self.dim))
        return results

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed text queries into the same 768-d space as images."""
        results: list[list[float]] = []
        for text in texts:
            # Tokenize words for semantic overlap matching
            clean_words = [
                w.strip(".,!?:;\"'()[]{}")
                for w in text.lower().split()
                if len(w.strip(".,!?:;\"'()[]{}")) > 1
            ]
            results.append(_semantic_mock_vector(clean_words or [text], dim=self.dim))
        return results


class ImageEmbeddingService:
    """Multimodal image-text embedding service utilizing SigLIP."""

    _instance: ImageEmbeddingService | None = None

    def __init__(self) -> None:
        self.model_name: str = settings.effective_image_embedding_model
        self.dim: int = SIGLIP_DIM
        self.model: Any = None
        self.processor: Any = None
        self._loaded: bool = False
        self.device: str = "cpu"

    @classmethod
    def get_instance(cls) -> ImageEmbeddingService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def unload(self) -> None:
        """Unload SigLIP model and processor weights from memory."""
        self.model = None
        self.processor = None
        self._loaded = False
        logger.info("Unloaded SigLIP image embedder from memory", model=self.model_name)

    def load(self) -> None:
        """Lazy model loader respecting MOCK_MODELS, hardware profile, and model manager."""
        from app.services.model_manager import get_model_manager

        model_mgr = get_model_manager()
        if self._loaded:
            model_mgr.mark_used("image_embedder")
            return

        with model_mgr.track_load("image_embedder"):
            if settings.MOCK_MODELS:
                logger.info(
                    "Initializing MockImageEmbedder",
                    model=self.model_name,
                    dim=self.dim,
                )
                self.model = MockImageEmbedder(dim=self.dim)
                self.device = "mock"
                self._loaded = True
                model_mgr.register_loaded("image_embedder", self, self.unload)
                return

            logger.info("Loading SigLIP model and processor", model=self.model_name)
            try:
                import torch
                from transformers import AutoModel, AutoProcessor

                device = (
                    "cuda" if torch.cuda.is_available() and settings.PROFILE != "cpu" else "cpu"
                )
                processor = AutoProcessor.from_pretrained(self.model_name)
                model = AutoModel.from_pretrained(self.model_name).to(device)
                model.eval()

                self.processor = processor
                self.model = model
                self.device = device
                self._loaded = True
                model_mgr.register_loaded("image_embedder", self, self.unload)
                logger.info("SigLIP model loaded successfully", device=self.device)
            except Exception as e:
                logger.error(
                    "Failed loading SigLIP model; falling back to MockImageEmbedder",
                    error=str(e),
                )
                self.model = MockImageEmbedder(dim=self.dim)
                self.device = "mock"
                self._loaded = True
                model_mgr.register_loaded("image_embedder", self, self.unload)

    def _prepare_pil_image(self, img_input: Path | str | Image.Image | bytes) -> Image.Image:
        """Ensure input is converted safely to a PIL RGB image."""
        if isinstance(img_input, Image.Image):
            return img_input.convert("RGB")
        if isinstance(img_input, (str, Path)):
            return Image.open(str(img_input)).convert("RGB")
        if isinstance(img_input, bytes):
            return Image.open(io.BytesIO(img_input)).convert("RGB")
        raise ValueError(f"Unsupported image input type: {type(img_input)}")

    def embed_images(
        self, images: list[Path | str | Image.Image | bytes]
    ) -> tuple[list[list[float]], float]:
        """Generate normalized 768-d SigLIP vectors for a list of images."""
        self.load()
        from app.services.model_manager import get_model_manager

        model_mgr = get_model_manager()
        model_mgr.mark_used("image_embedder")

        start_time = time.perf_counter()
        with model_mgr.acquire_inference_sync(), track("image_embedder", "embed_images") as tracker:
            if settings.MOCK_MODELS or isinstance(self.model, MockImageEmbedder):
                vectors = self.model.embed_images(images)
                latency_ms = (time.perf_counter() - start_time) * 1000.0
                tracker.set_tokens(count=len(images))
                return vectors, latency_ms

            import torch

            pil_images = [self._prepare_pil_image(img) for img in images]
            inputs = self.processor(images=pil_images, return_tensors="pt").to(self.device)
            with torch.no_grad():
                image_features = self.model.get_image_features(**inputs)
                image_features = image_features / image_features.norm(dim=-1, keepdim=True)
                vectors = image_features.cpu().tolist()

            latency_ms = (time.perf_counter() - start_time) * 1000.0
            tracker.set_tokens(count=len(images))
            return vectors, latency_ms

    def _translate_if_needed(self, text: str) -> str:
        """Translate non-English text to English with LLM for SigLIP cross-modal retrieval."""
        clean = text.strip()
        if not clean:
            return clean

        from app.services.vision_service import detect_language

        detected = detect_language(clean)
        # If explicitly non-English, translate via LLM (or mock map when in mock mode)
        if detected and detected not in ("en", "unknown"):
            if settings.MOCK_MODELS:
                mock_translations = {
                    "बजट": "budget",
                    "वार्षिक": "annual",
                    "वित्तीय": "financial",
                    "सौर": "solar",
                    "ऊर्जा": "energy",
                    "पैनल": "panel",
                    "आरेख": "diagram",
                    "खोज": "search",
                    "செயற்கை": "artificial",
                    "நுண்ணறிவு": "intelligence",
                    "தேடல்": "search",
                    "மருத்துவ": "medical",
                    "பாதுகாப்பு": "security",
                    "மென்பொருள்": "software",
                }
                words = clean.split()
                translated_words = [mock_translations.get(w, w) for w in words]
                return " ".join(translated_words)

            try:
                from app.services.llm_service import get_llm_service

                llm = get_llm_service()
                prompt = (
                    "Translate the following search query into concise English for image retrieval. "
                    "Output ONLY the translated English phrase with no extra punctuation or explanations.\n\n"
                    f"Query: {clean}"
                )
                translated, _ = llm.generate([{"role": "user", "content": prompt}], max_tokens=60)
                translated_clean = translated.strip()
                if translated_clean:
                    logger.info(
                        "Translated query for cross-modal SigLIP retrieval",
                        orig_len=len(clean),
                        trans_len=len(translated_clean),
                        src_lang=detected,
                    )
                    return translated_clean
            except Exception as e:
                logger.warning(
                    "Query translation failed; proceeding with original text",
                    error=str(e),
                )

        return clean

    def embed_text_for_images(self, texts: list[str]) -> tuple[list[list[float]], float]:
        """Generate normalized 768-d SigLIP vectors for text queries in image space."""
        self.load()
        from app.services.model_manager import get_model_manager

        model_mgr = get_model_manager()
        model_mgr.mark_used("image_embedder")

        # Multilingual handling: translate non-English queries to English
        processed_texts = [self._translate_if_needed(t) for t in texts]

        start_time = time.perf_counter()
        with model_mgr.acquire_inference_sync(), track("image_embedder", "embed_text") as tracker:
            if settings.MOCK_MODELS or isinstance(self.model, MockImageEmbedder):
                vectors = self.model.embed_texts(processed_texts)
                latency_ms = (time.perf_counter() - start_time) * 1000.0
                tracker.set_tokens(count=len(texts))
                return vectors, latency_ms

            import torch

            inputs = self.processor(
                text=processed_texts, padding="max_length", return_tensors="pt"
            ).to(self.device)
            with torch.no_grad():
                text_features = self.model.get_text_features(**inputs)
                text_features = text_features / text_features.norm(dim=-1, keepdim=True)
                vectors = text_features.cpu().tolist()

            latency_ms = (time.perf_counter() - start_time) * 1000.0
            tracker.set_tokens(count=len(texts))
            return vectors, latency_ms


def get_image_embedding_service() -> ImageEmbeddingService:
    """Retrieve singleton ImageEmbeddingService instance."""
    return ImageEmbeddingService.get_instance()
