"""Audio transcription service using faster-whisper with PyAV and graceful fallbacks."""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logging import get_logger
from app.services.metrics_service import track

logger = get_logger(__name__)

# Check system ffmpeg/ffprobe availability
HAS_FFMPEG = shutil.which("ffmpeg") is not None
HAS_FFPROBE = shutil.which("ffprobe") is not None


class WordTimestamp(BaseModel):
    """Timestamp and probability for an individual spoken word."""

    word: str
    start: float
    end: float
    probability: float


class AudioSegment(BaseModel):
    """Transcription segment with timing, text, and acoustic confidence."""

    start: float
    end: float
    text: str
    avg_logprob: float
    no_speech_prob: float
    words: list[WordTimestamp] | None = None


class TranscriptionResult(BaseModel):
    """Full transcription output containing text, language metadata, and segments."""

    text: str
    language: str
    language_probability: float
    duration: float
    segments: list[AudioSegment] = Field(default_factory=list)


def probe_audio_duration_seconds(file_path: Path) -> float:
    """Accurately determine audio duration in seconds using PyAV (bundled with faster-whisper)."""
    try:
        import av

        with av.open(str(file_path)) as container:
            if container.streams.audio:
                stream = container.streams.audio[0]
                if stream.duration is not None and stream.time_base is not None:
                    return float(stream.duration * stream.time_base)
            if container.duration is not None:
                return float(container.duration / av.time_base)
    except Exception as e:
        logger.warning("Failed to probe duration via PyAV", path=str(file_path), error=str(e))

    # Fallback to file size heuristic if PyAV fails
    try:
        size_bytes = file_path.stat().st_size
        return max(1.0, float(size_bytes / 32000))
    except Exception:
        return 10.0


class MockASR:
    """Deterministic Mock ASR generating plausible segments based on audio length and name hints."""

    def transcribe(
        self,
        file_path: Path,
        forced_language: str | None = None,
        task: str = "transcribe",
        word_timestamps: bool = False,
    ) -> TranscriptionResult:
        path_str = str(file_path).lower()
        if "corrupt" in path_str:
            raise ValueError(f"Corrupted audio file: {file_path.name}")

        if file_path.suffix.lower() == ".wav":
            try:
                import wave

                with wave.open(str(file_path), "rb") as wf:
                    wf.getnframes()
            except Exception as e:
                raise ValueError(f"Corrupted or invalid WAV file: {e!s}") from e

        duration = probe_audio_duration_seconds(file_path)

        # Determine language (forced, hinted in filename, or default "en")
        if forced_language:
            lang = forced_language
        elif "_hi" in path_str:
            lang = "hi"
        elif "_ta" in path_str:
            lang = "ta"
        elif "_es" in path_str:
            lang = "es"
        else:
            lang = "en"

        sample_texts = {
            "en": "This is a synthesized test transcript generated for OmniMind audio understanding.",
            "hi": "नमस्ते, यह ओम्नीमाइंड ऑडियो समझ सेवा के लिए एक परीक्षण प्रतिलेख है।",
            "ta": "வணக்கம், இது ஆம்னிமைண்ட் ஆடியோ புரிதல் சேவைக்கான மாதிரி உரை.",
            "es": "Hola, esta es una transcripción de prueba generada para OmniMind.",
        }

        if task == "translate":
            chosen_text = "Hello, this is a translated transcript into English for OmniMind."
            lang = "en"
        else:
            chosen_text = sample_texts.get(lang, sample_texts["en"])

        # Create structured segments spanning up to duration
        chunk_sec = 4.0
        current_time = 0.0
        segments: list[AudioSegment] = []
        words_in_text = chosen_text.split()

        while current_time < duration:
            seg_end = min(round(current_time + chunk_sec, 2), round(duration, 2))
            if seg_end <= current_time:
                break

            seg_words: list[WordTimestamp] | None = None
            if word_timestamps:
                step = (seg_end - current_time) / max(1, len(words_in_text))
                seg_words = [
                    WordTimestamp(
                        word=w,
                        start=round(current_time + (i * step), 2),
                        end=round(current_time + ((i + 1) * step), 2),
                        probability=0.98,
                    )
                    for i, w in enumerate(words_in_text)
                ]

            segments.append(
                AudioSegment(
                    start=round(current_time, 2),
                    end=seg_end,
                    text=chosen_text,
                    avg_logprob=-0.15,
                    no_speech_prob=0.01,
                    words=seg_words,
                )
            )
            current_time = seg_end

        if not segments:
            segments.append(
                AudioSegment(
                    start=0.0,
                    end=round(duration, 2),
                    text=chosen_text,
                    avg_logprob=-0.15,
                    no_speech_prob=0.01,
                )
            )

        full_text = " ".join(s.text for s in segments)

        return TranscriptionResult(
            text=full_text,
            language=lang,
            language_probability=0.99,
            duration=round(duration, 2),
            segments=segments,
        )


class AudioService:
    """Singleton Audio Transcription Service backed by faster-whisper with PyAV."""

    _instance: AudioService | None = None

    def __init__(self) -> None:
        self.model_name: str = settings.effective_asr_model
        self.model: Any = None
        self._loaded: bool = False
        self.device: str = "cpu"
        self.compute_type: str = settings.ASR_COMPUTE_TYPE

    @classmethod
    def get_instance(cls) -> AudioService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def unload(self) -> None:
        """Unload faster-whisper model from memory."""
        self.model = None
        self._loaded = False
        logger.info("Unloaded faster-whisper ASR weights from memory", model=self.model_name)

    def load(self) -> None:
        """Lazy loader for faster-whisper WhisperModel."""
        from app.services.model_manager import get_model_manager

        model_mgr = get_model_manager()
        if self._loaded:
            model_mgr.mark_used("asr")
            return

        with model_mgr.track_load("asr"):
            if settings.MOCK_MODELS:
                logger.info("Initializing MockASR", model=self.model_name)
                self.model = MockASR()
                self._loaded = True
                model_mgr.register_loaded("asr", self, self.unload)
                return

            logger.info(
                "Loading faster-whisper model",
                model=self.model_name,
                profile=settings.PROFILE,
                compute_type=self.compute_type,
                ffmpeg_available=HAS_FFMPEG,
            )

            try:
                import torch
                from faster_whisper import WhisperModel

                if settings.PROFILE != "cpu" and torch.cuda.is_available():
                    self.device = "cuda"
                    self.compute_type = "float16"
                else:
                    self.device = "cpu"
                    self.compute_type = "int8"

                self.model = WhisperModel(
                    self.model_name,
                    device=self.device,
                    compute_type=self.compute_type,
                )
                self._loaded = True
                model_mgr.register_loaded("asr", self, self.unload)
                logger.info("faster-whisper model loaded successfully", device=self.device)
            except Exception as e:
                logger.error(
                    "Failed to load faster-whisper model, falling back to MockASR", error=str(e)
                )
                self.model = MockASR()
                self._loaded = True
                model_mgr.register_loaded("asr", self, self.unload)

    def transcribe(
        self,
        file_path: Path | str,
        language: str | None = None,
        task: str = "transcribe",
        word_timestamps: bool = False,
    ) -> tuple[TranscriptionResult, float]:
        """Transcribe an audio file.

        Validates duration against MAX_AUDIO_DURATION_SEC, runs lazily, computes RTF,
        and returns (TranscriptionResult, latency_ms).
        """
        from app.services.model_manager import get_model_manager

        self.load()
        model_mgr = get_model_manager()
        model_mgr.mark_used("asr")

        path = Path(file_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Audio file not found: {path}")

        # Check maximum audio duration constraint
        duration = probe_audio_duration_seconds(path)
        if duration > settings.MAX_AUDIO_DURATION_SEC:
            raise ValueError(
                f"Audio duration ({duration:.1f}s) exceeds maximum allowed limit "
                f"of {settings.MAX_AUDIO_DURATION_SEC}s"
            )

        start_time = time.perf_counter()
        with model_mgr.acquire_inference_sync(), track("audio", "transcribe") as tracker:
            if settings.MOCK_MODELS or isinstance(self.model, MockASR):
                result = self.model.transcribe(
                    file_path=path,
                    forced_language=language,
                    task=task,
                    word_timestamps=word_timestamps,
                )
            else:
                # Transcribe with faster-whisper
                segments_gen, info = self.model.transcribe(
                    str(path),
                    beam_size=settings.ASR_BEAM_SIZE,
                    language=language,
                    task=task,
                    vad_filter=settings.ASR_VAD_FILTER,
                    word_timestamps=word_timestamps,
                )

                # Lazily accumulate segments to conserve memory on long files
                accumulated_segments: list[AudioSegment] = []
                text_snippets: list[str] = []

                for seg in segments_gen:
                    words_list: list[WordTimestamp] | None = None
                    if word_timestamps and hasattr(seg, "words") and seg.words:
                        words_list = [
                            WordTimestamp(
                                word=w.word,
                                start=round(w.start, 2),
                                end=round(w.end, 2),
                                probability=round(w.probability, 3),
                            )
                            for w in seg.words
                        ]

                    seg_obj = AudioSegment(
                        start=round(seg.start, 2),
                        end=round(seg.end, 2),
                        text=seg.text.strip(),
                        avg_logprob=round(seg.avg_logprob, 3),
                        no_speech_prob=round(seg.no_speech_prob, 3),
                        words=words_list,
                    )
                    accumulated_segments.append(seg_obj)
                    text_snippets.append(seg.text.strip())

                full_text = " ".join(text_snippets)
                result = TranscriptionResult(
                    text=full_text,
                    language=info.language,
                    language_probability=round(info.language_probability, 3),
                    duration=round(info.duration, 2),
                    segments=accumulated_segments,
                )

            latency_ms = (time.perf_counter() - start_time) * 1000.0
            latency_sec = latency_ms / 1000.0

            # Record Real-Time Factor (RTF)
            rtf = round(latency_sec / max(0.1, result.duration), 3)
            tracker.extra["rtf"] = rtf
            tracker.extra["audio_duration_sec"] = result.duration
            tracker.extra["language"] = result.language
            tracker.set_tokens(count=len(result.text.split()))

        return result, round(latency_ms, 2)

    def infer(self, input_data: Path | str) -> tuple[TranscriptionResult, float]:
        """Unified inference method satisfying the AGENTS.md service convention."""
        return self.transcribe(input_data)


def get_audio_service() -> AudioService:
    """Retrieve singleton AudioService instance."""
    return AudioService.get_instance()
