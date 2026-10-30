"""LLM inference service with hardware profile awareness, streaming, and JSON extraction."""

from __future__ import annotations

import asyncio
import json
import re
import threading
import time
from collections.abc import AsyncGenerator
from typing import Any, TypeVar

from pydantic import BaseModel

from app.core.config import settings
from app.core.logging import get_logger
from app.services.metrics_service import track

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


def extract_json_from_text(text: str) -> str:
    """Extract a JSON object or array from LLM output, stripping markdown fences."""
    # Look for ```json ... ``` or ``` ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()

    # Look for outermost { ... } or [ ... ]
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return text[first_brace : last_brace + 1].strip()

    first_bracket = text.find("[")
    last_bracket = text.rfind("]")
    if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
        return text[first_bracket : last_bracket + 1].strip()

    return text.strip()


class MockLLM:
    """Deterministic Mock LLM for offline tests and development without GPU/weights."""

    def __init__(self, model_id: str):
        self.model_id = model_id

    def generate(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> str:
        last_user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user_msg = m.get("content", "")
                break

        # Check if the prompt asks for specific json structures
        lower_prompt = last_user_msg.lower()
        if "title" in lower_prompt and "json" in lower_prompt:
            return json.dumps({"title": "OmniMind Conversation"})
        if "rewritten" in lower_prompt or "standalone" in lower_prompt:
            # Query rewriter mock
            return json.dumps(
                {
                    "rewritten_query": last_user_msg.split("<<<USER_CONTENT>>>")[-1]
                    .split("<<<")[0]
                    .strip()
                    or last_user_msg
                }
            )
        if "summary" in lower_prompt:
            return "This is a rolling summary of the earlier conversation topics."

        system_msg = ""
        for m in messages:
            if m.get("role") == "system":
                system_msg = m.get("content", "")
                break

        # Check for modality error notes
        if "NOTICE OF MODALITY ERRORS" in system_msg or "failed to process" in system_msg:
            return (
                "I processed your request, but please note that some attachments could not be processed due to errors. "
                "Specifically, an audio file could not be processed. "
                "I have analyzed the remaining valid attachments and image content."
            )

        # Synthesize inline citations for present media attachments
        citations: list[str] = []
        for m in messages:
            c = m.get("content", "")
            for f in re.findall(r'<<<IMAGE file="([^"]+)"', c):
                citations.append(f"[image:{f}]")
            for f in re.findall(r'<<<AUDIO file="([^"]+)"', c):
                citations.append(f"[audio:{f} 00:05]")

        citation_str = f" References: {' '.join(citations)}" if citations else ""

        return (
            f"Hello! I am OmniMind, running in mock mode. "
            f"I received your request regarding: '{last_user_msg[:80]}'.{citation_str}"
        )

    async def stream_generate(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        full_text = self.generate(messages, max_tokens, temperature)
        # Yield words with small delay to simulate streaming
        tokens = re.split(r"(\s+)", full_text)
        for token in tokens:
            if token:
                await asyncio.sleep(0.01)
                yield token


class LLMService:
    """Singleton LLM service managing model lifecycle and multi-backend inference."""

    _instance: LLMService | None = None

    def __init__(self) -> None:
        self.model_name: str = settings.effective_llm_model
        self.backend_type: str = "mock" if settings.MOCK_MODELS else "transformers"
        self.model: Any = None
        self.tokenizer: Any = None
        self._loaded: bool = False
        self.device: str = "cpu"

    @classmethod
    def get_instance(cls) -> LLMService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def unload(self) -> None:
        """Unload LLM model and tokenizer weights from memory."""
        self.model = None
        self.tokenizer = None
        self._loaded = False
        self.backend_type = "mock" if settings.MOCK_MODELS else "transformers"
        logger.info("Unloaded LLM weights from memory", model=self.model_name)

    def load(self) -> None:
        """Lazy model loader choosing backend based on PROFILE and installed libraries."""
        from app.services.model_manager import get_model_manager

        model_mgr = get_model_manager()
        if self._loaded:
            model_mgr.mark_used("llm")
            return

        with model_mgr.track_load("llm"):
            if settings.MOCK_MODELS:
                logger.info("Initializing MockLLM", model=self.model_name)
                self.model = MockLLM(model_id=self.model_name)
                self.backend_type = "mock"
                self._loaded = True
                model_mgr.register_loaded("llm", self, self.unload)
                return

            # Check for optional GGUF model path via llama-cpp-python
            if settings.GGUF_MODEL_PATH and settings.PROFILE == "cpu":
                try:
                    from llama_cpp import Llama  # type: ignore[import-not-found,import-untyped]

                    logger.info(
                        "Loading GGUF model via llama-cpp-python",
                        path=settings.GGUF_MODEL_PATH,
                    )
                    self.model = Llama(
                        model_path=settings.GGUF_MODEL_PATH,
                        n_ctx=settings.CONTEXT_LENGTH_LIMIT,
                        verbose=False,
                    )
                    self.backend_type = "llama_cpp"
                    self._loaded = True
                    model_mgr.register_loaded("llm", self, self.unload)
                    return
                except ImportError:
                    logger.warning(
                        "llama-cpp-python not installed; falling back to transformers for CPU"
                    )

            # Transformers backend
            try:
                import torch
                from transformers import AutoModelForCausalLM, AutoTokenizer

                logger.info(
                    "Loading Transformers model",
                    model=self.model_name,
                    profile=settings.PROFILE,
                )
                self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)

                if settings.PROFILE == "cpu":
                    self.device = "cpu"
                    self.model = AutoModelForCausalLM.from_pretrained(
                        self.model_name,
                        torch_dtype=torch.float32,
                        low_cpu_mem_usage=True,
                    )
                else:
                    self.device = "cuda" if torch.cuda.is_available() else "cpu"
                    # Check for 4-bit quantization on GPU
                    quantization_config = None
                    if self.device == "cuda":
                        try:
                            from transformers import BitsAndBytesConfig

                            quantization_config = BitsAndBytesConfig(
                                load_in_4bit=True,
                                bnb_4bit_compute_dtype=torch.float16,
                                bnb_4bit_quant_type="nf4",
                            )
                            logger.info("Using 4-bit BitsAndBytes quantization")
                        except (ImportError, Exception):
                            quantization_config = None

                    load_kwargs: dict[str, Any] = {
                        "torch_dtype": (torch.float16 if self.device == "cuda" else torch.float32),
                        "device_map": "auto" if self.device == "cuda" else None,
                    }
                    if quantization_config:
                        load_kwargs["quantization_config"] = quantization_config

                    self.model = AutoModelForCausalLM.from_pretrained(
                        self.model_name, **load_kwargs
                    )

                self.backend_type = "transformers"
                self._loaded = True
                model_mgr.register_loaded("llm", self, self.unload)
                logger.info(
                    "LLM loaded successfully",
                    model=self.model_name,
                    backend=self.backend_type,
                )
            except Exception as e:
                logger.error(
                    "Failed to load real LLM model; falling back to MockLLM",
                    error=str(e),
                )
                self.model = MockLLM(model_id=self.model_name)
                self.backend_type = "mock"
                self._loaded = True
                model_mgr.register_loaded("llm", self, self.unload)

    def generate(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> tuple[str, float]:
        """Generate response text for chat messages. Returns (output_text, timing_ms)."""
        from app.services.model_manager import get_model_manager

        self.load()
        model_mgr = get_model_manager()
        model_mgr.mark_used("llm")
        start = time.perf_counter()
        with model_mgr.acquire_inference_sync():
            with track("llm", "generate") as tracker:
                if self.backend_type == "mock":
                    out = self.model.generate(
                        messages, max_tokens=max_tokens, temperature=temperature
                    )
                    tracker.set_tokens(count=len(out.split()))
                elif self.backend_type == "llama_cpp":
                    resp = self.model.create_chat_completion(
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    out = resp["choices"][0]["message"]["content"]
                    tracker.set_tokens(
                        count=resp.get("usage", {}).get("completion_tokens", len(out.split()))
                    )
                else:
                    prompt_text = self.tokenizer.apply_chat_template(
                        messages, tokenize=False, add_generation_prompt=True
                    )
                    inputs = self.tokenizer(prompt_text, return_tensors="pt").to(self.device)
                    input_len = inputs["input_ids"].shape[1]
                    output_ids = self.model.generate(
                        **inputs,
                        max_new_tokens=max_tokens,
                        temperature=temperature,
                        do_sample=temperature > 0,
                        pad_token_id=self.tokenizer.eos_token_id,
                    )
                    gen_ids = output_ids[0][input_len:]
                    out = self.tokenizer.decode(gen_ids, skip_special_tokens=True)
                    tracker.set_tokens(count=len(gen_ids), prompt_tokens=input_len)

            timing_ms = (time.perf_counter() - start) * 1000.0
        return out, round(timing_ms, 2)

    async def stream_generate(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        """Async generator streaming tokens in real time without blocking event loop."""
        from app.services.model_manager import get_model_manager

        self.load()
        get_model_manager().mark_used("llm")
        if self.backend_type == "mock":
            async for token in self.model.stream_generate(messages, max_tokens, temperature):
                yield token
            return

        # Real transformers streaming via TextIteratorStreamer & queue
        from transformers import TextIteratorStreamer

        prompt_text = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self.tokenizer(prompt_text, return_tensors="pt").to(self.device)

        streamer = TextIteratorStreamer(self.tokenizer, skip_prompt=True, skip_special_tokens=True)
        gen_kwargs = {
            **inputs,
            "streamer": streamer,
            "max_new_tokens": max_tokens,
            "temperature": temperature,
            "do_sample": temperature > 0,
            "pad_token_id": self.tokenizer.eos_token_id,
        }

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        def run_generation() -> None:
            try:
                self.model.generate(**gen_kwargs)
            except Exception as e:
                logger.error("Error during streaming generation", error=str(e))
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        def streamer_worker() -> None:
            for new_text in streamer:
                loop.call_soon_threadsafe(queue.put_nowait, new_text)

        gen_thread = threading.Thread(target=run_generation, daemon=True)
        worker_thread = threading.Thread(target=streamer_worker, daemon=True)

        gen_thread.start()
        worker_thread.start()

        while True:
            token = await queue.get()
            if token is None:
                break
            yield token

    def generate_json(
        self,
        prompt: str,
        pydantic_schema: type[T],
        max_retries: int = 2,
    ) -> tuple[T, float]:
        """Generate and validate a structured JSON object against a Pydantic schema with repair retries."""
        self.load()
        start = time.perf_counter()
        schema_desc = json.dumps(pydantic_schema.model_json_schema(), indent=2)
        system_instruction = (
            "You are a structured data generator. You MUST respond with ONLY valid JSON "
            f"conforming to the following JSON schema:\n{schema_desc}\n"
            "Do NOT include any explanatory text, markdown code blocks, or comments outside the JSON."
        )

        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt},
        ]

        # Fast-path for MockLLM: if mock mode, inspect fields and build default or parsed object
        if self.backend_type == "mock":
            # Attempt to generate mock response or construct dummy
            raw_text = self.model.generate(messages)
            try:
                clean_json = extract_json_from_text(raw_text)
                parsed = pydantic_schema.model_validate_json(clean_json)
                return parsed, round((time.perf_counter() - start) * 1000.0, 2)
            except Exception:
                # Synthesize valid schema instance
                dummy_data: dict[str, Any] = {}
                for field_name, field_info in pydantic_schema.model_fields.items():
                    if field_info.annotation is str or field_info.annotation == str | None:
                        dummy_data[field_name] = f"mock_{field_name}"
                    elif field_info.annotation is int:
                        dummy_data[field_name] = 1
                    elif field_info.annotation is bool:
                        dummy_data[field_name] = False
                    elif (
                        field_info.annotation is list
                        or getattr(field_info.annotation, "__origin__", None) is list
                    ):
                        dummy_data[field_name] = []
                    else:
                        dummy_data[field_name] = None
                parsed = pydantic_schema.model_validate(dummy_data)
                return parsed, round((time.perf_counter() - start) * 1000.0, 2)

        last_error: str = ""
        current_prompt = prompt

        for attempt in range(max_retries + 1):
            if attempt > 0:
                messages = [
                    {"role": "system", "content": system_instruction},
                    {
                        "role": "user",
                        "content": (
                            f"{current_prompt}\n\n"
                            f"ATTENTION: Your previous attempt failed validation with error: {last_error}.\n"
                            f"Please return ONLY valid JSON matching this schema: {schema_desc}"
                        ),
                    },
                ]

            raw_text, _ = self.generate(messages, max_tokens=1024, temperature=0.1)
            clean_json = extract_json_from_text(raw_text)

            try:
                parsed_instance = pydantic_schema.model_validate_json(clean_json)
                timing_ms = (time.perf_counter() - start) * 1000.0
                return parsed_instance, round(timing_ms, 2)
            except Exception as val_err:
                last_error = str(val_err)
                logger.warning(
                    "JSON schema validation failed",
                    attempt=attempt,
                    error=last_error,
                )

        timing_ms = (time.perf_counter() - start) * 1000.0
        raise ValueError(
            f"Failed to generate valid JSON conforming to {pydantic_schema.__name__} after {max_retries} retries. "
            f"Last error: {last_error}"
        )

    def infer(self, input_data: list[dict[str, str]] | str) -> tuple[str, float]:
        """Unified ML model inference method returning (text, timing_ms)."""
        if isinstance(input_data, str):
            messages = [{"role": "user", "content": input_data}]
        else:
            messages = input_data
        return self.generate(messages)


def get_llm_service() -> LLMService:
    """Retrieve singleton LLMService instance."""
    return LLMService.get_instance()
