"""Visual Language Model (VLM) Service supporting SmolVLM and Qwen2-VL.

Provides image description, Visual Question Answering (VQA), OCR text extraction,
structured data extraction, and deterministic MockVLM.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, TypeVar, cast

from PIL import Image
from pydantic import BaseModel

from app.core.config import settings
from app.core.logging import get_logger
from app.services.llm_service import extract_json_from_text
from app.services.metrics_service import track
from app.utils.lang import detect_language

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


class MockVLM:
    """Deterministic Mock VLM for fast local testing without GPU/checkpoint downloads."""

    def describe(self, image: Image.Image, detail_level: str = "brief") -> str:
        w, h = image.size
        if detail_level == "detailed":
            return (
                f"A detailed scene ({w}x{h} pixels). The image displays balanced lighting, "
                "clear foreground subjects, and well-defined spatial composition with distinct coloration."
            )
        return f"A clear image of {w}x{h} pixels with prominent visual objects and balanced composition."

    def answer(
        self,
        image: Image.Image,
        question: str,
        history: list[dict[str, Any]] | None = None,
    ) -> str:
        w, h = image.size
        q_lower = question.lower()
        detected_lang = detect_language(question)

        # Multilingual response generation
        if detected_lang == "hi":
            return f"इस {w}x{h} छवि के विश्लेषण के आधार पर, आपके प्रश्न का उत्तर सकारात्मक है।"
        elif detected_lang == "ta":
            return f"இந்த {w}x{h} படத்தின் பகுப்பாய்வின் அடிப்படையில், உங்கள் கேள்விக்கான பதில் நேர்மறையானது."

        # English deterministic responses
        if "color" in q_lower:
            return "The image contains distinct dominant colors with prominent hue contrasts."
        elif "text" in q_lower or "read" in q_lower or "say" in q_lower:
            return "The image contains legible text elements positioned in the scene."
        elif "how many" in q_lower or "count" in q_lower:
            return "There appear to be 2 primary objects visible in the foreground."

        context_suffix = (
            f" (Context from {len(history)} previous turns considered)" if history else ""
        )
        return (
            f"Based on the visual composition of this {w}x{h} image, the answer to '{question}' "
            f"is clearly visible in the central frame.{context_suffix}"
        )

    def extract_text(self, image: Image.Image) -> str:
        w, h = image.size
        return f"Visual text extracted from image coordinates [0, 0, {w}, {h}]."

    def structured_extract(self, image: Image.Image, schema: type[T]) -> T | dict[str, Any]:
        # Return default/dummy instance of requested Pydantic schema
        try:
            return schema()  # type: ignore[call-arg]
        except Exception:
            return {}


class VisionService:
    """Singleton Vision Language Model Service."""

    _instance: VisionService | None = None

    def __init__(self) -> None:
        self.model_name: str = settings.effective_vlm_model
        self.model: Any = None
        self.processor: Any = None
        self.backend_type: str = "smolvlm"  # "smolvlm" or "qwen2_vl"
        self._loaded: bool = False
        self.device: str = "cpu"

    @classmethod
    def get_instance(cls) -> VisionService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def unload(self) -> None:
        """Unload VLM model and processor weights from memory."""
        self.model = None
        self.processor = None
        self._loaded = False
        logger.info("Unloaded VLM weights from memory", model=self.model_name)

    def load(self) -> None:
        """Lazy load VLM backend based on profile and configured checkpoint."""
        from app.services.model_manager import get_model_manager

        model_mgr = get_model_manager()
        if self._loaded:
            model_mgr.mark_used("vlm")
            return

        with model_mgr.track_load("vlm"):
            if settings.MOCK_MODELS:
                logger.info("Initializing MockVLM", model=self.model_name)
                self.model = MockVLM()
                self._loaded = True
                model_mgr.register_loaded("vlm", self, self.unload)
                return

            logger.info("Loading Vision Language Model", model=self.model_name)
            try:
                import torch

                if settings.PROFILE != "cpu" and torch.cuda.is_available():
                    self.device = "cuda"
                else:
                    self.device = "cpu"

                # Determine backend architecture from model name
                lower_name = self.model_name.lower()
                if "qwen" in lower_name:
                    self.backend_type = "qwen2_vl"
                    from transformers import (
                        AutoProcessor,
                        Qwen2VLForConditionalGeneration,
                    )

                    load_kwargs: dict[str, Any] = {
                        "torch_dtype": (torch.float16 if self.device == "cuda" else torch.float32),
                    }
                    if self.device == "cuda":
                        load_kwargs["device_map"] = "auto"

                    self.processor = AutoProcessor.from_pretrained(self.model_name)
                    self.model = Qwen2VLForConditionalGeneration.from_pretrained(
                        self.model_name, **load_kwargs
                    )
                    if self.device == "cpu":
                        self.model.to("cpu")
                else:
                    # Default to SmolVLM
                    self.backend_type = "smolvlm"
                    try:
                        from transformers import (
                            AutoModelForImageTextToText as AutoModelForVision2Seq,
                        )
                        from transformers import (
                            AutoProcessor,
                        )
                    except ImportError:
                        from transformers import (  # type: ignore[attr-defined,no-redef]
                            AutoModelForVision2Seq,
                            AutoProcessor,
                        )

                    self.processor = AutoProcessor.from_pretrained(self.model_name)
                    self.model = AutoModelForVision2Seq.from_pretrained(
                        self.model_name,
                        torch_dtype=(torch.float32 if self.device == "cpu" else torch.float16),
                    )
                    self.model.to(self.device)

                self.model.eval()
                self._loaded = True
                model_mgr.register_loaded("vlm", self, self.unload)
                logger.info(
                    "Successfully loaded VLM",
                    model=self.model_name,
                    backend=self.backend_type,
                    device=self.device,
                )
            except Exception as e:
                logger.warning(
                    "Failed to load real VLM checkpoint, falling back to MockVLM",
                    error=str(e),
                )
                self.model = MockVLM()
                self._loaded = True
                model_mgr.register_loaded("vlm", self, self.unload)

    def describe(
        self,
        image: Image.Image | Path | str,
        detail_level: str = "brief",
    ) -> tuple[str, float]:
        """Generate caption description of image (brief or detailed)."""
        from app.services.model_manager import get_model_manager

        self.load()
        model_mgr = get_model_manager()
        model_mgr.mark_used("vlm")
        pil_image = (
            image if isinstance(image, Image.Image) else Image.open(str(image)).convert("RGB")
        )

        prompt = (
            "Describe this image thoroughly and in detail."
            if detail_level == "detailed"
            else "Provide a concise, direct description of this image in one or two sentences."
        )

        start_time = time.perf_counter()
        with model_mgr.acquire_inference_sync(), track("vision", "describe") as tracker:
            if settings.MOCK_MODELS or isinstance(self.model, MockVLM):
                result = self.model.describe(pil_image, detail_level=detail_level)
            else:
                result = self._generate_vlm(pil_image, prompt)

            latency_ms = (time.perf_counter() - start_time) * 1000.0
            tracker.set_tokens(count=len(result.split()))

        return result, round(latency_ms, 2)

    def answer(
        self,
        image: Image.Image | Path | str,
        question: str,
        history: list[dict[str, Any]] | None = None,
    ) -> tuple[str, float]:
        """Answer question about image using VLM with optional conversation history."""
        from app.services.model_manager import get_model_manager

        self.load()
        model_mgr = get_model_manager()
        model_mgr.mark_used("vlm")
        pil_image = (
            image if isinstance(image, Image.Image) else Image.open(str(image)).convert("RGB")
        )

        # Determine user query language to instruct model to answer in the same language
        user_lang = detect_language(question)
        lang_instruction = (
            f" Please respond in Hindi ({user_lang})."
            if user_lang == "hi"
            else f" Please respond in Tamil ({user_lang})." if user_lang == "ta" else ""
        )

        history_context = ""
        if history:
            history_lines = [
                f"{msg.get('role', 'user')}: {msg.get('content', '')}" for msg in history[-6:]
            ]
            history_context = "\nConversation Context:\n" + "\n".join(history_lines) + "\n\n"

        prompt = f"{history_context}Question about image: {question}{lang_instruction}"

        start_time = time.perf_counter()
        with model_mgr.acquire_inference_sync(), track("vision", "answer") as tracker:
            if settings.MOCK_MODELS or isinstance(self.model, MockVLM):
                result = self.model.answer(pil_image, question, history=history)
            else:
                result = self._generate_vlm(pil_image, prompt)

            latency_ms = (time.perf_counter() - start_time) * 1000.0
            tracker.set_tokens(count=len(result.split()))

        return result, round(latency_ms, 2)

    def extract_text(self, image: Image.Image | Path | str) -> tuple[str, float]:
        """Perform OCR-style text reading from image using VLM."""
        from app.services.model_manager import get_model_manager

        self.load()
        model_mgr = get_model_manager()
        model_mgr.mark_used("vlm")
        pil_image = (
            image if isinstance(image, Image.Image) else Image.open(str(image)).convert("RGB")
        )

        prompt = (
            "Read and extract all visible text, numbers, signage, and labels present in this image verbatim. "
            "If no text is visible, output '<no_text>'."
        )

        start_time = time.perf_counter()
        with model_mgr.acquire_inference_sync(), track("vision", "extract_text") as tracker:
            if settings.MOCK_MODELS or isinstance(self.model, MockVLM):
                result = self.model.extract_text(pil_image)
            else:
                raw_text = self._generate_vlm(pil_image, prompt)
                result = "" if "<no_text>" in raw_text else raw_text.strip()

            latency_ms = (time.perf_counter() - start_time) * 1000.0
            tracker.set_tokens(count=len(result.split()))

        return result, round(latency_ms, 2)

    def structured_extract(
        self,
        image: Image.Image | Path | str,
        schema: type[T],
    ) -> tuple[T | dict[str, Any], float]:
        """Extract structured information conforming to a Pydantic schema from image."""
        self.load()
        pil_image = (
            image if isinstance(image, Image.Image) else Image.open(str(image)).convert("RGB")
        )

        schema_json = schema.model_json_schema()
        prompt = (
            f"Analyze the image and return a strictly valid JSON object adhering to this schema:\n"
            f"{schema_json}\nReturn ONLY the JSON object, without explanation."
        )

        start_time = time.perf_counter()
        with track("vision", "structured_extract"):
            if settings.MOCK_MODELS or isinstance(self.model, MockVLM):
                result = self.model.structured_extract(pil_image, schema)
            else:
                raw_response = self._generate_vlm(pil_image, prompt)
                extracted_dict = extract_json_from_text(raw_response)
                try:
                    result = schema.model_validate(extracted_dict)
                except Exception:
                    result = extracted_dict

            latency_ms = (time.perf_counter() - start_time) * 1000.0

        return result, round(latency_ms, 2)

    def _generate_vlm(self, image: Image.Image, prompt: str) -> str:
        """Internal dispatch to appropriate VLM backend generation."""
        import torch

        if self.backend_type == "qwen2_vl":
            from qwen_vl_utils import process_vision_info

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image},
                        {"type": "text", "text": prompt},
                    ],
                }
            ]
            text = self.processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            image_inputs, video_inputs = process_vision_info(messages)
            inputs = self.processor(
                text=[text],
                images=image_inputs,
                videos=video_inputs,
                padding=True,
                return_tensors="pt",
            ).to(self.device)

            with torch.no_grad():
                generated_ids = self.model.generate(
                    **inputs, max_new_tokens=settings.VLM_MAX_NEW_TOKENS
                )

            trimmed = [
                out_ids[len(in_ids) :] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
            ]
            decoded_text = self.processor.batch_decode(
                trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
            )[0]
            return cast(str, decoded_text).strip()
        else:
            # SmolVLM
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image"},
                        {"type": "text", "text": prompt},
                    ],
                }
            ]
            prompt_text = self.processor.apply_chat_template(messages, add_generation_prompt=True)
            inputs = self.processor(text=prompt_text, images=[image], return_tensors="pt").to(
                self.device
            )

            with torch.no_grad():
                generated_ids = self.model.generate(
                    **inputs, max_new_tokens=settings.VLM_MAX_NEW_TOKENS
                )

            trimmed = [
                out_ids[len(in_ids) :] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
            ]
            decoded_smol = self.processor.batch_decode(trimmed, skip_special_tokens=True)[0]
            return cast(str, decoded_smol).strip()

    def infer(self, input_data: Image.Image | Path | str) -> tuple[str, float]:
        """Unified inference method satisfying AGENTS.md conventions."""
        return self.describe(input_data)


def get_vision_service() -> VisionService:
    """Retrieve singleton VisionService instance."""
    return VisionService.get_instance()
