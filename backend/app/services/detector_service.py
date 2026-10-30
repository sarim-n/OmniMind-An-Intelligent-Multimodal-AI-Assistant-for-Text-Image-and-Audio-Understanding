"""Object Detection service using RT-DETR (strictly Apache-2.0).

Supports bounding box detection, category counting, OpenCV visualization, and deterministic MockDetector.
"""

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.vision import DetectedObject, DetectionResult
from app.services.metrics_service import track

logger = get_logger(__name__)


class MockDetector:
    """Deterministic Mock Object Detector generating plausible bounding boxes based on image dimensions."""

    def detect(
        self,
        image: Image.Image,
        threshold: float = settings.DETECTOR_THRESHOLD,
    ) -> DetectionResult:
        width, height = image.size
        objects: list[DetectedObject] = []

        if width >= 100 and height >= 100:
            # Deterministic object 1: person
            objects.append(
                DetectedObject(
                    label="person",
                    confidence=0.92,
                    bbox=[
                        round(width * 0.1, 1),
                        round(height * 0.15, 1),
                        round(width * 0.45, 1),
                        round(height * 0.85, 1),
                    ],
                )
            )
            # Deterministic object 2: laptop
            objects.append(
                DetectedObject(
                    label="laptop",
                    confidence=0.86,
                    bbox=[
                        round(width * 0.4, 1),
                        round(height * 0.5, 1),
                        round(width * 0.85, 1),
                        round(height * 0.88, 1),
                    ],
                )
            )

        # Filter by threshold
        filtered = [obj for obj in objects if obj.confidence >= threshold]
        counts = dict(Counter(obj.label for obj in filtered))
        return DetectionResult(objects=filtered, counts=counts)


class DetectorService:
    """Singleton Object Detection Service backed by RT-DETR."""

    _instance: DetectorService | None = None

    def __init__(self) -> None:
        self.model_name: str = settings.effective_detector_model
        self.model: Any = None
        self.processor: Any = None
        self._loaded: bool = False
        self.device: str = "cpu"

    @classmethod
    def get_instance(cls) -> DetectorService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def load(self) -> None:
        """Lazy loader for RT-DETR model and image processor."""
        if self._loaded:
            return

        if settings.MOCK_MODELS:
            logger.info("Initializing MockDetector", model=self.model_name)
            self.model = MockDetector()
            self._loaded = True
            return

        logger.info("Loading RT-DETR object detector", model=self.model_name)
        try:
            import torch
            from transformers import AutoImageProcessor, AutoModelForObjectDetection

            if settings.PROFILE != "cpu" and torch.cuda.is_available():
                self.device = "cuda"
            else:
                self.device = "cpu"

            self.processor = AutoImageProcessor.from_pretrained(self.model_name)
            self.model = AutoModelForObjectDetection.from_pretrained(self.model_name)
            self.model.to(self.device)
            self.model.eval()
            self._loaded = True
            logger.info(
                "Successfully loaded RT-DETR detector",
                model=self.model_name,
                device=self.device,
            )
        except Exception as e:
            logger.warning(
                "Failed to load real RT-DETR detector, falling back to MockDetector",
                error=str(e),
            )
            self.model = MockDetector()
            self._loaded = True

    def detect(
        self,
        image: Image.Image | Path | str,
        threshold: float = settings.DETECTOR_THRESHOLD,
    ) -> tuple[DetectionResult, float]:
        """Detect objects in image and return (DetectionResult, latency_ms)."""
        self.load()

        if isinstance(image, (str, Path)):
            pil_image = Image.open(str(image)).convert("RGB")
        else:
            pil_image = image.convert("RGB")

        start_time = time.perf_counter()
        with track("vision", "detect") as tracker:
            if settings.MOCK_MODELS or isinstance(self.model, MockDetector):
                result = self.model.detect(pil_image, threshold=threshold)
            else:
                import torch

                inputs = self.processor(images=pil_image, return_tensors="pt").to(self.device)
                with torch.no_grad():
                    outputs = self.model(**inputs)

                target_sizes = torch.tensor([pil_image.size[::-1]]).to(self.device)
                raw_results = self.processor.post_process_object_detection(
                    outputs, target_sizes=target_sizes, threshold=threshold
                )[0]

                detected_objects: list[DetectedObject] = []
                for score, label_id, box in zip(
                    raw_results["scores"], raw_results["labels"], raw_results["boxes"]
                ):
                    label_name = self.model.config.id2label.get(
                        label_id.item(), str(label_id.item())
                    )
                    confidence = round(float(score.item()), 3)
                    coords = [round(float(c), 1) for c in box.tolist()]
                    detected_objects.append(
                        DetectedObject(label=label_name, confidence=confidence, bbox=coords)
                    )

                counts = dict(Counter(obj.label for obj in detected_objects))
                result = DetectionResult(objects=detected_objects, counts=counts)

            latency_ms = (time.perf_counter() - start_time) * 1000.0
            tracker.extra["object_count"] = len(result.objects)
            tracker.extra["categories"] = list(result.counts.keys())

        return result, round(latency_ms, 2)

    def draw_annotations(
        self,
        image: Image.Image,
        objects: list[DetectedObject],
        output_path: Path | str,
    ) -> Path:
        """Draw bounding boxes and confidence labels using OpenCV and write to output_path."""
        out_path = Path(output_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        rgb_arr = np.array(image.convert("RGB"))
        bgr = cv2.cvtColor(rgb_arr, cv2.COLOR_RGB2BGR)

        # Distinct color palette for boxes
        palette = [
            (0, 220, 0),  # Green
            (255, 100, 0),  # Blue
            (0, 140, 255),  # Orange
            (200, 0, 200),  # Purple
            (0, 215, 255),  # Yellow
            (50, 50, 240),  # Red
        ]

        for i, obj in enumerate(objects):
            color = palette[i % len(palette)]
            x1, y1, x2, y2 = [round(v) for v in obj.bbox]

            # Draw bounding rectangle
            cv2.rectangle(bgr, (x1, y1), (x2, y2), color, 2)

            # Draw text label with confidence badge
            label_text = f"{obj.label} {int(obj.confidence * 100)}%"
            (tw, th), _baseline = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)

            # Badge background
            badge_y1 = max(0, y1 - th - 6)
            badge_y2 = max(th + 6, y1)
            cv2.rectangle(bgr, (x1, badge_y1), (x1 + tw + 6, badge_y2), color, -1)

            # Badge text
            cv2.putText(
                bgr,
                label_text,
                (x1 + 3, badge_y2 - 3),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 0, 0),
                1,
                cv2.LINE_AA,
            )

        cv2.imwrite(str(out_path), bgr)
        return out_path

    def infer(self, input_data: Image.Image | Path | str) -> tuple[DetectionResult, float]:
        """Unified inference method satisfying AGENTS.md conventions."""
        return self.detect(input_data)


def get_detector_service() -> DetectorService:
    """Retrieve singleton DetectorService instance."""
    return DetectorService.get_instance()
